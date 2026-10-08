import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cyberscientist import db
row=db.query_one('SELECT mailbox_id FROM submissions WHERE id=?',('sub_8e446f6e58',));before=db.query_one('SELECT COUNT(*) FROM submissions')[0]
args=[sys.executable,str(ROOT/'.runtime/cyberscientist_launch.py'),'ops','submit','--target','comp','--dry-run','--run-id','run_8a21b7d249','--trial-id','trial_04dc15406d','--mailbox-id',row['mailbox_id'],'--package-path','submissions/sub_8e446f6e58/package.zip','--operation-id','hidden-runtime-preview']
process=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=300)
after=db.query_one('SELECT COUNT(*) FROM submissions')[0]
result={'exit_code':process.returncode,'stdout':process.stdout,'stderr':process.stderr,'submission_count_before':before,'submission_count_after':after}
(ROOT/'.runtime/validation/hidden/preview.json').write_text(json.dumps(result,indent=2))
assert process.returncode==0 and before==after
print(json.dumps({'built':True,'submissions_before':before,'submissions_after':after}))
