import base64
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import tester_access as access


def config(**overrides):
    data = {"sub":"senior","exp":int(time.time()+86400),"video":{"roomJoin":True,"room":"senior-lobby",
            "canPublish":False,"canPublishData":False,"canSubscribe":False}}
    data.update(overrides)
    body = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
    return {"schema":1,"host":"test.livekit.cloud","lobbyToken":"header."+body+".signature"}


class AccessTests(unittest.TestCase):
    def test_rejects_api_like_overbroad_wrong_identity_and_expired_tokens(self):
        good = config()
        self.assertEqual(access.validate(good)[0],"test.livekit.cloud")
        for bad in (config(sub='other'),config(exp=time.time()-1),config(exp=time.time()+9*86400),
                    config(video={"roomJoin":True,"room":"all-rooms","canPublish":True})):
            with self.assertRaises(ValueError): access.validate(bad)

    def test_install_preserves_signing_and_never_creates_backend_secrets(self):
        with tempfile.TemporaryDirectory() as t:
            target=Path(t)/'Local.xcconfig';target.write_text('DEVELOPMENT_TEAM = PERSONAL\n')
            source=Path(t)/access.FILENAME;source.write_text(json.dumps(config()))
            with patch.object(access,'CONFIG',target): access.install(source)
            text=target.read_text()
            self.assertIn('DEVELOPMENT_TEAM = PERSONAL',text)
            self.assertIn('CALLMA_DEMO = false',text)
            self.assertNotIn('API_SECRET',text)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)

    def test_issue_artifact_has_only_host_and_limited_signed_app_token(self):
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ,LIVEKIT_URL='wss://test.livekit.cloud',
                LIVEKIT_API_KEY='unit-test-key',LIVEKIT_API_SECRET='unit-test-secret-at-least-32-bytes'):
            path=Path(t)/access.FILENAME
            access.issue(path)
            data=json.loads(path.read_text())
            self.assertEqual(set(data),{'schema','host','lobbyToken'})
            self.assertNotIn(os.environ['LIVEKIT_API_SECRET'],path.read_text())
            from livekit import api
            self.assertEqual(api.TokenVerifier().verify(data['lobbyToken']).identity,'senior')
            access.validate(data)

    def test_download_uses_only_main_private_artifact_and_validates_zip(self):
        import io,zipfile
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr(access.FILENAME,json.dumps(config()))
        metadata={'artifacts':[{'id':7,'name':access.ARTIFACT,'expired':False,'created_at':'2026-10-17',
                                'workflow_run':{'head_branch':'main'}},
                               {'id':9,'name':access.ARTIFACT,'expired':False,'created_at':'2026-10-18',
                                'workflow_run':{'head_branch':'untrusted'}}]}
        with patch.object(access,'gh_api',side_effect=[json.dumps(metadata).encode(),out.getvalue()]) as api:
            access.validate(access.download())
            self.assertEqual(api.call_args.args[0],f'repos/{access.REPO}/actions/artifacts/7/zip')


if __name__=='__main__':unittest.main()
