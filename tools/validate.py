"""Validate canonical facts, editorial groups, public channels and generated views."""
import argparse
from datetime import date
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse
from company_routes import redirects
from record_checks import load, normalized_organization_name, record_path, reject_placeholders, schema_validator, today, validate_record

ROOT=Path(__file__).resolve().parents[1]
PHOTO_LIMIT=400*1024


def iso_day(text):
    return date.fromisoformat(text+('-01-01' if len(text)==4 else '-01' if len(text)==7 else ''))


def validate_data(root=ROOT):
    root=Path(root).resolve()
    platforms=load(root/'data/lists/incumbents.json')
    schema_validator('platform-universe.schema.json',root).validate(platforms)
    reject_placeholders(platforms)
    assert len(platforms['platforms'])==len({p['id'] for p in platforms['platforms']}),'Duplicate platform IDs'
    assert iso_day(platforms['checked_at'])<=today(),'Future platform-universe check'
    for p in platforms['platforms']:
        assert iso_day(p['checked_at'])<=iso_day(platforms['checked_at']),'Platform check is after universe date'
        for evidence in p.get('topic_evidence',[]):
            assert iso_day(evidence['checked_at'])<=iso_day(p['checked_at']),'Topic evidence is newer than seed check'
            if evidence['published_date']:
                assert iso_day(evidence['published_date'])<=iso_day(evidence['checked_at']),'Topic publication is after its check'
    tax=load(root/'data/taxonomy.json')
    schema_validator('taxonomy.schema.json',root).validate(tax)
    categories=[c['id'] for c in tax['categories']]
    assert len(categories)==len(set(categories)),'Duplicate category IDs'
    assert iso_day(tax['version'])<=today(),'Future taxonomy revision'
    all_records=[]
    for path in sorted((root/'data/companies').glob('*.json')):
        r=load(path);validate_record(r,root);all_records.append(r)
        kind=r['organization_type']
        assert record_path(root,kind,path.stem)==path,'Invalid canonical path'
        assert r['id']==path.stem,'Record identity does not match its canonical path'
        assert len(r['aliases'])==len(set(r['aliases'])),'Duplicate aliases'
        if kind=='operating_organization':
            assert r['category_id'] in categories,'Unknown category'
            if not r['contacts']['careers_url'] or not r['contacts']['recruitment_email']:
                assert r['notes'],'Missing contacts require scope notes'
        else:
            if r['founded']['year'] is not None:
                assert r['founded']['year']<=iso_day(r['checked_at']).year,'Future foundation year'
        for source in r['sources']:
            if source['published_date']:
                assert iso_day(source['published_date'])<=iso_day(source['checked_at']),'Publication is after the claimed check'
            assert urlparse(source['url']).hostname,'Invalid source URL'
        if r['contacts']['other_email']:
            assert r['contacts']['other_email_purpose'],'Other email needs its purpose'
    assert all_records,'Empty company dataset'
    assert len(all_records)==len({r['id'] for r in all_records}),'Duplicate company IDs across types'
    assert len(all_records)==len({r['name'] for r in all_records}),'Duplicate company names across types'
    redirects(root)
    validate_platform_bindings(platforms, all_records)
    photos=validate_person_photos(all_records,root)
    print('Validated %d stored person photos under data/views/assets/people.'%photos)
    for kind in ('operating_organization','investment_firm'):
        records=[r for r in all_records if r['organization_type']==kind]
        if kind=='operating_organization':
            assert len(records)==len({r['provenance']['original_name'] for r in records}),'Duplicate imported identity'
        print('Validated %d %s and %d source records.'%(len(records),kind,sum(len(r['sources']) for r in records)))
    validate_vc_list(root)
    assert not (root/'data/investors').exists(),'Use data/companies for every complete company profile'
    assert not (root/'data/platforms.json').exists(),'Use data/lists/incumbents.json for discovery seeds'
    return all_records


def validate_person_photos(records, root=ROOT):
    """Every stored portrait must exist under data/views and stay small enough for the static view."""
    root=Path(root).resolve()
    views=(root/'data/views').resolve()
    checked=0
    for record in records:
        for person in record.get('people', []):
            photo=person.get('photo')
            if not photo:continue
            path=(views/photo['path']).resolve()
            assert views in path.parents,'Person photo must be stored inside data/views: '+photo['path']
            assert path.is_file(),'Missing person photo file: '+photo['path']
            assert path.stat().st_size<PHOTO_LIMIT,'Person photo must stay under 400 KB: '+photo['path']
            checked+=1
    return checked


def validate_platform_bindings(platforms, records):
    records={r['id']:r for r in records}
    for seed in platforms['platforms']:
        if 'company_id' not in seed:continue
        assert seed['company_id'] in records,'Platform route refers to missing company'
        record=records[seed['company_id']]
        context=record.get('organizational_context',{})
        assert context.get('form') not in {'internal_team','research_lab','product_project'},'Platform seed cannot route to a child unit or project instead of the same-level company'
        seed_names={normalized_organization_name(n) for n in [seed['name'],*seed['aliases']]}
        company_names={normalized_organization_name(n) for n in [record['name'],*record['aliases']]}
        assert seed_names & company_names,'Platform route needs a matching evidenced organization identity'


def validate_vc_list(root=ROOT):
    root=Path(root)
    listing=load(root/'data/lists/vcs.json')
    schema_validator('vc-list.schema.json',root).validate(listing)
    reject_placeholders(listing)
    ids=[entry['company_id'] for entry in listing['entries']]
    assert len(ids)==len(set(ids)),'Duplicate VC discovery memberships'
    for entry in listing['entries']:
        r=load(record_path(root,'investment_firm',entry['company_id']))
        assert r['id']==entry['company_id'] and r['organization_type']=='investment_firm','VC list must reference an investment-firm company'
        sources={source['id']:source for source in r['sources']}
        assert set(entry['source_ids'])<=sources.keys(),'VC list refers to missing company evidence'
        assert all(sources[s].get('scope','organization')=='organization' for s in entry['source_ids']),'VC discovery requires company evidence, not channel-only sources'
    return listing



def validate_links(root=ROOT):
    root=Path(root).resolve()
    paths=[root/'AGENTS.md',root/'README.md']
    for folder in ('data','skills','tools'):paths.extend(sorted((root/folder).rglob('*.md')))
    for path in paths:
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text()):
            if target.startswith(('https://','http://','mailto:','#')):continue
            resolved=(path.parent/unquote(target.split('#',1)[0])).resolve()
            assert root==resolved or root in resolved.parents,'Local link escapes shared repository'
            assert resolved.exists(),'Broken local link: '+str(path.relative_to(root))+' -> '+target


def validate_indexes(root=ROOT):
    root=Path(root).resolve()
    index=load(root/'data/index.json')
    schema_validator('index.schema.json',root).validate(index)
    keys=set()
    for entry in index['organizations']:
        key=(entry['organization_type'],entry['id'])
        assert key not in keys,'Duplicate unified-index identity'
        keys.add(key)
        assert entry['json_path']==record_path(root,*key).relative_to(root).as_posix(),'Wrong canonical index path'
        for field in ('json_path','markdown_path'):
            path=(root/entry[field]).resolve()
            assert root in path.parents and path.is_file(),'Broken machine-index path: '+entry[field]
    assert index['counts']['organizations']==len(keys),'Wrong unified-index count'
    assert not any((root/p).exists() for p in ['data/targets.json','data/investor-index.json']),'Retired indexes must not be recreated'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-generated',action='store_true');args=p.parse_args()
    records=validate_data()
    if args.check_generated:
        subprocess.run([sys.executable,str(ROOT/'tools/build.py'),'--check'],check=True)
        validate_indexes()
    validate_links()
    print('Editorial first-wave candidates: %d; no placeholder or draft records accepted.'%sum(r['targeting']['wave']=='first' for r in records))
if __name__=='__main__':main()
