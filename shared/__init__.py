"""shared - FSx for ONTAP S3 Access Points 共通モジュール

全ユースケースで共有する ONTAP REST API クライアント、FSx API ヘルパー、
S3 Access Point ヘルパー、共通例外クラスを提供する。

Usage:
    from shared import OntapClient, OntapClientConfig, OntapClientError
    from shared import FsxHelper, FsxHelperError
    from shared import S3ApHelper, S3ApHelperError, lambda_error_handler
"""

from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError
from shared.fsx_helper import FsxHelper, FsxHelperError
from shared.s3ap_helper import S3ApHelper
from shared.exceptions import S3ApHelperError, lambda_error_handler

__all__ = [
    # ontap_client
    "OntapClient",
    "OntapClientConfig",
    "OntapClientError",
    # fsx_helper
    "FsxHelper",
    "FsxHelperError",
    # s3ap_helper
    "S3ApHelper",
    # exceptions
    "S3ApHelperError",
    "lambda_error_handler",
]
