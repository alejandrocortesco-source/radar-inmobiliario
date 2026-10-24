import json
from pathlib import Path
import pytest
from metro.extraction import (ExtractionError,canonical,detail_from_records,flight_records,
                              identity,listing_links,fingerprint,normalize_detail,sanitize)

@pytest.mark.parametrize('kind',['apartamento','oficina','consultorio'])
def test_real_public_detail(kind):
    fixture=json.loads((Path(__file__).parent/'fixtures'/f'{kind}.json').read_text(encoding='utf-8'))
    result=normalize_detail(fixture['raw'],fixture['url'],fixture['text'])
    assert result['quality']=='success'
    assert result['normalized']['property_type'].lower()==kind
    assert result['normalized']['id']==identity(fixture['url'])
    assert result['normalized']['price']>0
    assert len(result['normalized']['description'])>30
    assert result['photos']
    assert isinstance(result['features'],list)
    assert result['fields']['price']['raw']==fixture['raw']['salePrice']

def test_flight_split_references_and_long_text():
    long='Descripción de la propiedad\ncon dos líneas.'
    record='1:'+json.dumps({'propertyId':'ID','businessType':'venta','comment':'$2'})+'\n'
    text='2:T'+format(len(long.encode()),'x')+','+long
    stream=record+text
    scripts=['self.__next_f.push('+json.dumps([1,part])+')' for part in (stream[:19],stream[19:])]
    result=detail_from_records(flight_records(scripts),'ID')
    assert result['comment']==long

def test_listing_excludes_recommendations_and_deduplicates():
    a={'link':'/inmueble/apartamento/1-M1','midinmueble':'1-M1'}
    b={'link':'/inmueble/apartamento/2-M2','midinmueble':'2-M2'}
    batch={'results':[a,a],'highlights':[a],'recommended':[b]}
    assert [x['id'] for x in listing_links(batch)]==['1-M1']
    assert fingerprint(batch)==fingerprint({**batch,'highlights':[b]})

def test_absent_error_and_zero_are_distinct():
    raw={'propertyId':'X','businessType':'venta','rooms':None,'bathrooms':'desconocido','garages':'0'}
    result=normalize_detail(raw,'/inmueble/apartamento/X')
    assert result['normalized']['rooms'] is None
    assert result['fields']['rooms']['status']=='absent'
    assert result['normalized']['bathrooms'] is None
    assert result['fields']['bathrooms']['status']=='error'
    assert result['normalized']['garages']==0
    assert result['quality']=='partial'
    assert result['normalized']['currency'] is None

def test_canonical_and_secrets():
    assert canonical('/inmueble/casa/1-M1?src_url=abc')=='https://www.metrocuadrado.com/inmueble/casa/1-M1'
    with pytest.raises(ExtractionError): canonical('https://example.com/inmueble/X')
    with pytest.raises(ExtractionError): identity('/inmueble/casa/X','Y')
    assert sanitize({'cookie':'x','nested':{'apiKey':'y','title':'Casa'},'url':'https://x.com/?token=abc&photo=1'})=={'nested':{'title':'Casa'},'url':'https://x.com/?photo=1'}
