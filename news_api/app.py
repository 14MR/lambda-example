import base64
import dataclasses
import json

import boto3
import pymongo
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.event_handler.exceptions import BadRequestError
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from bson.json_util import dumps, loads

logger = Logger(service="APP")

app = APIGatewayRestResolver()

news_secret_name = "documentDB"
news_region_name = "eu-west-2"


@dataclasses.dataclass
class NewsItem:
    date: str  # TODO: move to actual date type
    title: str
    description: str


def get_secret(secret_name, region_name):
    # Create a Secrets Manager client
    session = boto3.session.Session()
    boto_config = BotoConfig(
        connect_timeout=3,
        retries={
            "max_attempts": 3,
            "mode": "standard"
        }
    )
    boto3_client = session.client(
        service_name='secretsmanager',
        region_name=region_name,
        config=boto_config
    )

    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = boto3_client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS key.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            return get_secret_value_response['SecretString']
        else:
            return base64.b64decode(get_secret_value_response['SecretBinary'])


credentials = json.loads(get_secret(secret_name=news_secret_name, region_name=news_region_name))
client = pymongo.MongoClient(
    host=credentials['host'],
    username=credentials['username'],
    password=credentials['password'],
    tls='true',
    tlsAllowInvalidCertificates=True
)
db = client.sample_database
news = db['news']


@app.get("/news")
def list_news():
    return loads(dumps(news.find({}, {'_id': False})))


@app.post("/newsitem")
def add_newsitem():
    # since it's just one endpoint, pydantic is redundant here
    try:
        item = NewsItem(
            **app.current_event.json_body
        )
    except TypeError as e:
        raise BadRequestError("Invalid required parameters")

    news.insert_one(dataclasses.asdict(item))

    return {"status": "success"}


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    return app.resolve(event, context)
