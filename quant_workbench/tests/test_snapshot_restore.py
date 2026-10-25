import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec=importlib.util.spec_from_file_location('restore_snapshot',Path(__file__).resolve().parents[1]/'scripts/restore_github_snapshot.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def fixture_archive(tmp_path,entries):
    assets=tmp_path/'assets';assets.mkdir()
    archive=assets/'data.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for name,data in entries:z.writestr(name,data)
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'assets':[{'name':'data.zip','bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}],
        'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'asset':'data.zip'} for name,data in entries]}),encoding='utf8')
    return assets,manifest

def test_restore_checks_then_preserves_identical_files(tmp_path):
    assets,manifest=fixture_archive(tmp_path,[('research_library/example.txt',b'research')])
    root=tmp_path/'workspace'
    module.restore(assets,root,True,manifest)
    assert not root.exists()
    module.restore(assets,root,False,manifest)
    file=root/'research_library/example.txt';before=file.stat().st_mtime_ns
    module.restore(assets,root,False,manifest)
    assert file.read_bytes()==b'research' and file.stat().st_mtime_ns==before

def test_conflicting_local_file_prevents_all_writes(tmp_path):
    assets,manifest=fixture_archive(tmp_path,[('research_library/new.txt',b'new'),('research_library/existing.txt',b'snapshot')])
    root=tmp_path/'workspace';folder=root/'research_library';folder.mkdir(parents=True)
    (folder/'existing.txt').write_bytes(b'user modified')
    with pytest.raises(ValueError,match='refusing overwrite'):module.restore(assets,root,False,manifest)
    assert not (folder/'new.txt').exists()
    assert (folder/'existing.txt').read_bytes()==b'user modified'

def test_archive_traversal_is_rejected(tmp_path):
    assets,manifest=fixture_archive(tmp_path,[('research_library/../../escape.txt',b'bad')])
    with pytest.raises(ValueError,match='Unsafe archive path'):module.restore(assets,tmp_path/'workspace',False,manifest)
    assert not (tmp_path/'escape.txt').exists()

def test_modified_archive_is_rejected_before_restore(tmp_path):
    assets,manifest=fixture_archive(tmp_path,[('research_library/example.txt',b'research')])
    with (assets/'data.zip').open('ab') as f:f.write(b'tampered')
    with pytest.raises(ValueError,match='Archive checksum mismatch'):module.restore(assets,tmp_path/'workspace',False,manifest)
