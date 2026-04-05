from aiobotocore.session import get_session
from app.core.config import settings


class MinioClient:
    def __init__(self):
        self.session = get_session()
        self.endpoint_url = settings.MINIO_URL
        self.access_key = settings.MINIO_USER
        self.secret_key = settings.MINIO_PASSWORD

    def get_client(self):
        return self.session.create_client(
            's3',
            region_name='us-east-1',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key
        )


minio_manager = MinioClient()
