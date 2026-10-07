import zipfile
from pathlib import Path

from .prepare_v6 import unpack_bundle


def test_changed_archive_cannot_retain_deleted_evidence_files(tmp_path):
    archive=tmp_path/'.raw/bundles/1.zip';archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('root/old_output.txt','old result');z.writestr('root/README.md','first')
    old,digest1=unpack_bundle(tmp_path,'1')
    assert (Path(old)/'old_output.txt').exists()
    with zipfile.ZipFile(archive,'w') as z:z.writestr('root/README.md','second')
    current,digest2=unpack_bundle(tmp_path,'1')
    assert digest1!=digest2 and old!=current and not (Path(current)/'old_output.txt').exists()
    assert (Path(current)/'README.md').read_text()=='second'
