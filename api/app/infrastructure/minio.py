import json
import uuid

import botocore
from aiobotocore.session import get_session
from app.core.config import settings


class MinioClient:
    def __init__(self):
        self.session = get_session()
        self.endpoint_url = settings.MINIO_URL
        self.access_key = settings.MINIO_USER
        self.secret_key = settings.MINIO_PASSWORD
        self.bucket_name = settings.MINIO_BUCKET_NAME

    def get_client(self):
        return self.session.create_client(
            's3',
            region_name='us-east-1',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key
        )

    async def ensure_bucket_exists(self):
        async with self.get_client() as client:
            try:
                await client.head_bucket(Bucket=self.bucket_name)
            except botocore.exceptions.ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    print('Bucket does not exist. Creating new bucket...')
                    await client.create_bucket(Bucket=self.bucket_name)

                    policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "PublicReadGetObject",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["s3:GetObject"],
                                "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"]
                            }
                        ]
                    }
                    await client.put_bucket_policy(Bucket=self.bucket_name, Policy=json.dumps(policy))
                else:
                    raise e

    async def upload_file(self, file_bytes: bytes, original_filename: str, content_type: str) -> str:
        file_extension = original_filename.split(".")[-1] if "." in original_filename else "enc"
        unique_filename = f"{uuid.uuid4()}.{file_extension}"

        async with self.get_client() as client:
            await client.put_object(
                Bucket=self.bucket_name,
                Key=unique_filename,
                Body=file_bytes,
                ContentType=content_type
            )

            file_url = f"{self.endpoint_url}/{self.bucket_name}/{unique_filename}"
            return file_url
            

minio_manager = MinioClient()
