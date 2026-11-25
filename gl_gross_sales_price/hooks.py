def post_init_hook(env):
    """Initialize the stored gross price when the module is installed fresh."""
    products = env["product.template"].with_context(active_test=False).search([])
    products._gl_initialize_stored_gross_prices()
