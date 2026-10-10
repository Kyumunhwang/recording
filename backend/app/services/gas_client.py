"""Client for dispatching counseling sessions to Central Google Apps Script Webhook."""
import httpx
from typing import Dict, Any
from app.core.config import settings
from app.models.schemas import SessionRecord

class GASClient:
    """Sends completed session summaries and diarized transcripts to Google Apps Script."""

    def __init__(self):
        self.webhook_url = settings.GAS_WEBHOOK_URL

    async def sync_session(self, record: SessionRecord) -> Dict[str, Any]:
        """
        Sends payload to GAS Webhook.
        If webhook URL is empty, simulates a successful Google Drive/Docs route for preview.
        """
        if not self.webhook_url:
            # Simulated preview link when webhook is not yet deployed by user
            return {
                "status": "success",
                "simulated": True,
                "message": "Local preview mode: GAS URL not configured yet.",
                "docUrl": f"https://docs.google.com/document/d/mock-{record.sessionId}/edit",
                "teacherFolderUrl": f"https://drive.google.com/drive/folders/mock-{record.teacherEmail}"
            }

        payload = {
            "action": "SYNC_COUNSELING_RECORD",
            "teacherEmail": record.teacherEmail,
            "teacherName": record.teacherName,
            "session": {
                "sessionId": record.sessionId,
                "studentName": record.studentName,
                "topic": record.topic,
                "counselingDate": record.counselingDate,
                "duration": record.durationFormatted
            },
            "transcript": [t.model_dump() for t in (record.transcript or [])],
            "summary": record.summary.model_dump() if record.summary else {}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to sync with Google Drive: {str(e)}"
                }

gas_client = GASClient()
