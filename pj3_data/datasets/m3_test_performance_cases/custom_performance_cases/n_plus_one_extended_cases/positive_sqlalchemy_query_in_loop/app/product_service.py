from app.models import Product


def get_product_names(product_ids, session):
    names = []
    for product_id in product_ids:
        product = session.query(Product).filter(Product.id == product_id).first()
        names.append(product.name if product else None)
    return names
