# -*- coding: utf-8 -*-
import os, sys
import time
import json
from kafka import (KafkaClient, SimpleProducer)
import find_company

reload(sys)
sys.setdefaultencoding("utf-8")
sys.path.append(os.path.join(os.path.split(os.path.realpath(__file__))[0], '../../../util'))
sys.path.append(os.path.join(os.path.split(os.path.realpath(__file__))[0], '../../support'))
import config
import loghelper
import db

sys.path.append(os.path.join(os.path.split(os.path.realpath(__file__))[0], '../util'))
import aggregator_db_util

import company_aggregator_baseinfo
import company_aggregator_artifact
import company_aggregator_member
import company_aggregator_funding
import company_aggregator_footprint
import company_aggregator_job

import corporate_aggregator

#logger
loghelper.init_logger("company_aggregator", stream=True)
logger = loghelper.get_logger("company_aggregator")

# kafka
kafkaProducer = None


def init_kafka():
    global kafkaProducer
    (url) = config.get_kafka_config()
    kafka = KafkaClient(url)
    # HashedPartitioner is default
    kafkaProducer = SimpleProducer(kafka)

def send_message(company_id, action):
    if kafkaProducer is None:
        init_kafka()

    #action: create, delete
    msg = {"type":"company", "id":company_id , "action":action, "from": "bamy"}
    flag = False
    while flag is False:
        try:
            kafkaProducer.send_messages("aggregator_v2", json.dumps(msg))
            flag = True
        except Exception,e :
            logger.exception(e)
            time.sleep(60)

def send_message_task(company_id, action, source):
    if kafkaProducer is None:
        init_kafka()

    #action: create, delete
    msg = {"source":action, "id":company_id , "detail":source}
    flag = False
    while flag is False:
        try:
            kafkaProducer.send_messages("task_company", json.dumps(msg))
            flag = True
        except Exception,e :
            logger.exception(e)
            time.sleep(60)


def set_sourcecompany_processstatus(source_company_id):
    conn = db.connect_torndb()
    conn.update("update source_company set processStatus=2 where id=%s", source_company_id)
    conn.close()

# def send_message(company_id):
#     msg = {"type":"company", "id":company_id}
#     flag = False
#     while flag is False:
#         try:
#             kafkaProducer.send_messages("aggregator_v2", json.dumps(msg))
#             flag = True
#         except Exception,e :
#             logger.exception(e)
#             time.sleep(60)


def aggregator(source_company, test=False):
    sc = source_company
    source_company_id = sc["id"]

    #find company_id
    if not test:
        company_id = sc["companyId"]
        if company_id is not None:
            logger.info("sourceCompanyId=%s has been merged before.", source_company_id)
        else:
            if sc["aggregateGrade"] == 1:
                company_id = find_company.find_company_grade2(sc)
            elif sc["source"] in [13120]:
                company_id = find_company.find_reference(sc)
            elif sc["source"] in [13400,13401,13402]:
                company_id = find_company.find_company_grade2(sc)
            else:
                company_id = find_company.find_company_new(sc)
    else:
        #test
        # company_id = find_company.find_company(sc, test)
        return

    logger.info("matched company_id=%s", company_id)

    #merge company base info
    if company_id is None:
        if source_company['source'] == 13120:
            logger.info("reference")

        else:
            logger.info("sourceCompanyId=%s is a new company", source_company_id)
            company_id = company_aggregator_baseinfo.create_company(sc, test)
            logger.info("new company_id %s", company_id)

        if company_id is None:
            if not test:
                set_sourcecompany_processstatus(sc["id"])
            return
        else:
            if source_company["source"] not in [13099, 13050]:
                send_message_task(company_id,"company_newcover",source_company["source"])
            elif source_company["source"] in [13099]:
                send_message_task(company_id, "company_create", source_company["source"])

    else:
        if source_company['source'] == 13120:
            aggregator_db_util.update_source_company_found(company_id, source_company_id)
            set_sourcecompany_processstatus(sc["id"])
            return
        logger.info("sourceCompanyId=%s was found, companyId=%s", sc["id"], company_id)
        if not test:
            aggregator_db_util.update_source_company_found(company_id, source_company_id)
            company_aggregator_baseinfo.aggregate(company_id, source_company_id,)

    conn = db.connect_torndb()
    company = conn.get("select * from company where id=%s", company_id)
    if company["corporateId"] is not None:
        corporate = conn.get("select * from corporate where id=%s", company["corporateId"])
    else:
        corporate = None
    conn.close()
    if company["modifyUser"] is not None and company["active"] is not None and company["active"] != 'P':
        logger.info("company %s modified", company["id"])
        company_aggregator_artifact.aggregate_artifact(company_id, source_company_id, test)
        company_aggregator_member.aggregate_member(company_id, source_company_id, test)
        # set_sourcecompany_processstatus(sc["id"])
        # return

    else:
        #merge others
        company_aggregator_artifact.aggregate_artifact(company_id, source_company_id, test)
        company_aggregator_member.aggregate_member(company_id, source_company_id, test)
        # company_aggregator_funding.aggregate_funding(company_id, sc, test)
        if not test:
            company_aggregator_footprint.aggregate_footprint(company_id, source_company_id)
            #company_aggregator_job.aggregate_job(company_id, source_company_id)
        #news ITjuzi news parser直接聚合, toutian单独聚合

        company_aggregator_baseinfo.add_company_alias(company_id, source_company_id, test)

    if not test:
        # conn = db.connect_torndb()
        # company = conn.get("select * from company where id=%s", company_id)
        # conn.close()

        if company["verify"] == "Y" or (
                    company["modifyUser"] is not None and company["active"] is not None and company["active"] != 'P'):

            pass
        else:
            company_aggregator_baseinfo.patch_company_establish_date(company_id)
            company_aggregator_baseinfo.patch_company_location(company_id)
            company_aggregator_baseinfo.patch_company_fullname(company_id)
            company_aggregator_baseinfo.patch_company_status(company_id)
            company_aggregator_baseinfo.patch_website(company_id)
            company_aggregator_baseinfo.patch_logo(company_id)
            company_aggregator_baseinfo.patch_should_index(company_id)

        if corporate is not None and corporate["modifyUser"] is not None and \
                 corporate["active"] is not None and corporate["active"] != 'P':
            logger.info("corporate %s modified", corporate["id"])
            if source_company["source"] in [13400, 13401, 13402, 13030, 13022]:
                # add corporate_alias
                corporate_aggregator.add_corporate_alias(source_company_id, company_id, corporate["id"])
        else:
            # insert company_corporate or update company_corporate
            corporate_id = corporate_aggregator.update_corporate(company_id)
            # add corporate_alias
            corporate_aggregator.add_corporate_alias(source_company_id, company_id, corporate_id)
            # add funding corporateId
            corporate_aggregator.add_funding_corporateId(company_id, corporate_id)
            # set corporateId
            corporate_aggregator.set_corporateId(company_id,corporate_id)
            company_aggregator_baseinfo.patch_corporate_fullname(corporate_id)

        #double add company fullName
        if company["verify"] == "Y" or (
                    company["modifyUser"] is not None and company["active"] is not None and company["active"] != 'P'):
            pass
        else:
            company_aggregator_baseinfo.patch_company_fullname(company_id)
            # company_aggregator_baseinfo.patch_corporate_fullname(corporate_id)
        set_sourcecompany_processstatus(sc["id"])
        if sc["source"] in [13050]:
            mongo = db.connect_mongo()
            collection_company = mongo.job.company
            collection_company.update_one({"source": sc["source"],
                                           "sourceId":{"$in":[str(sc["sourceId"]),int(sc["sourceId"])]}},
                                          {"$set": {"mapChecked": None}})
            mongo.close()
        # send_message(company_id,"create")


if __name__ == '__main__':
    init_kafka()

    while True:
        logger.info("Company aggregator start...")
        conn = db.connect_torndb()
        scs = list(conn.query("select * from source_company where processStatus=1 and (active is null or active='Y') and source!=13002 order by id desc limit 100"))
        #scs = list(conn.query("select * from source_company where id=31098"))
        conn.close()

        for sc in scs:
            aggregator(sc)
            # break

        logger.info("Company aggregator end.")

        # break
        if len(scs) == 0:
            time.sleep(60)