"""푸시 알림. 발송 수단(FCM·가짜·없음)은 환경변수로 고른다. 자세한 설정은 docs/phase3-plan.md §5."""
from .base import PushMessage, PushResult, PushSender
from .config import get_sender, push_sender_dep, reset_sender
from .fake import FakePushSender
from .fcm import FcmPushSender
from .service import notify_user

__all__ = ["PushMessage", "PushResult", "PushSender", "FakePushSender", "FcmPushSender", "get_sender",
           "push_sender_dep", "reset_sender", "notify_user"]
