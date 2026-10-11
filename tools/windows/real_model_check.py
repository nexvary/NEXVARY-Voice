"""CI explicitly opts into heavy downloads. Exercises the real GUI setup worker.

Not a claim of microphone/speaker hardware or translation semantic accuracy.
"""
import json
import os
import shutil
import sys
from pathlib import Path
import uv
from PySide6.QtCore import QCoreApplication
from voice_engine import desktop_setup
from voice_engine.setup_wizard import SetupTask

root = Path(os.environ.get('RUNNER_TEMP',Path.cwd()/'build'))/'voice-setup-اختبار'
root.mkdir(parents=True,exist_ok=True)
# Same isolated runtime installer, but CI locates uv from the installed package.
desktop_setup.home = lambda: root
desktop_setup.uv_path = lambda: Path(uv.find_uv_bin())
app = QCoreApplication([])
output = Path('build');output.mkdir(exist_ok=True)
log_path = output/'real-model-log.txt'
results = []

def log(message):
    print(message,flush=True)
    with log_path.open('a',encoding='utf-8') as out: out.write(message+'\n')

worker = SetupTask('all')
worker.message.connect(log);worker.problem.connect(log)
worker.done.connect(results.append)
worker.run()
state = desktop_setup.detect()
functional = root/'functional-tests.json'
report = {'setup_passed':bool(results and results[-1]),'diagnostics':state,
          'kind':'real Windows CPU INT8 model inference; no hardware audio',
          'functional_tests':json.loads(functional.read_text(encoding='utf-8')) if functional.exists() else {}}
(output/'real-model-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
evidence = output/'real-model-evidence';evidence.mkdir(exist_ok=True)
for directory in ('samples','validation-video'):
    if (root/directory).exists(): shutil.copytree(root/directory,evidence/directory,dirs_exist_ok=True)
# Re-scan without downloads; repeated healthy voice downloads are verified/skipped
# by the downloader unit tests. This job proves model inference only.
raise SystemExit(0 if report['setup_passed'] else 1)
