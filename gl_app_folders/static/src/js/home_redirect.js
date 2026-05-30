/** @odoo-module **/

const TARGET_SELECTORS = [
    "[title='Platzhalter']",
    "[title='Placeholder']",
    "[aria-label='Platzhalter']",
    "[aria-label='Placeholder']",
    "[data-tooltip='Platzhalter']",
    "[data-tooltip='Placeholder']",
    ".o_main_navbar .o_menu_toggle",
    ".o_main_navbar .o_menu_brand",
    ".o_main_navbar .o_navbar_apps_menu",
].join(', ');

function isDesktopOpen() {
    return Boolean(document.querySelector('.gl_app_desktop'));
}

function handleNavbarHomeRedirect(ev) {
    const target = ev.target && ev.target.closest ? ev.target.closest(TARGET_SELECTORS) : null;
    if (!target) {
        return;
    }
    const navbar = target.closest('.o_main_navbar');
    if (!navbar) {
        return;
    }
    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();
    window.location.assign(isDesktopOpen() ? '/odoo' : '/gl_app_folders/desktop');
}

document.addEventListener('click', handleNavbarHomeRedirect, true);
