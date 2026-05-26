"""Write the rendered report to Blob Storage via managed identity."""

import logging
import os
from datetime import datetime, timezone

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)


def write_report(report_md: str) -> str:
    account = os.environ["REPORTS_STORAGE_ACCOUNT"]
    container = os.environ["REPORTS_CONTAINER"]

    blob_name = f"report-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')}.md"
    account_url = f"https://{account}.blob.core.windows.net"

    bsc = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    blob = bsc.get_blob_client(container=container, blob=blob_name)
    blob.upload_blob(report_md, overwrite=False)
    return f"{account_url}/{container}/{blob_name}"
