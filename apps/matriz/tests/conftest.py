from apps.catalogs.models import SystemCatalogItem


def item(catalog, code):
    return SystemCatalogItem.objects.get(catalog=catalog, code=code)
