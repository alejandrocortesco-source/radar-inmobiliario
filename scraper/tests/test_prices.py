import pytest
from metro.prices import price, same_price, listing_price, search_identity

@pytest.mark.parametrize('raw',[1000000,1000000.0,'1000000','$ 1.000.000 COP','COP 1,000,000.00','1.000.000,00','1,000,000'])
def test_equivalent_formats(raw):
    result=price(raw,'COP','venta')
    assert result['status']=='valid'
    assert result['amount']=='1000000'

@pytest.mark.parametrize('raw',[None,'',0,-1,True,float('nan'),float('inf'),'Desde $1000','1.234,567','0.123','1e6','1,2,3'])
def test_missing_or_ambiguous_prices_are_not_compared(raw):
    assert price(raw,'COP','venta')['status']=='uncomparable'

def test_currency_and_operation_must_match():
    a=price(1000,'COP','venta')
    assert not same_price(a,price(1000,'USD','venta'))
    assert not same_price(a,price(1000,'COP','arriendo'))
    assert price('$1000',None,'venta')['status']=='uncomparable'
    assert price('USD 1000','COP','venta')['reason']=='conflicting_currency'
    assert price('$1000',None,'venta',fallback_currency='COP')['currency_source']=='configured_search_currency'
    assert price('US$1000',None,'venta',fallback_currency='COP')['currency']=='USD'

def test_sale_and_lease_use_distinct_public_fields():
    item={'raw':{'mtiponegocio':'arriendo','mvalorventa':999,'mvalorarriendo':123,'currency':'COP'}}
    assert listing_price(item)['amount']=='123'

def test_search_tracking_does_not_create_a_new_search():
    assert search_identity('https://www.metrocuadrado.com/inmuebles/venta/bogota/?search=form&utm_source=x') == search_identity('https://www.metrocuadrado.com/inmuebles/venta/bogota')

def test_dual_offer_compares_the_sale_price_that_the_portal_lists():
    from metro.prices import detail_price
    from metro.extraction import normalize_detail
    item={'raw':{'mtiponegocio':'venta y arriendo','mvalorventa':1_000_000,'mvalorarriendo':1000}}
    raw={'propertyId':'1-M1','businessType':'Venta y Arriendo','salePrice':1_000_000,'rentPrice':1000}
    data=normalize_detail(raw,'/inmueble/apartamento/1-M1')
    assert data['normalized']['price']==1_000_000
    assert data['extra']['rentPrice']==1000
    assert same_price(listing_price(item,'COP'),detail_price(data,'COP'))
