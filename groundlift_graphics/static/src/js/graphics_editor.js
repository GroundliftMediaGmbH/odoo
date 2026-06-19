/** @odoo-module **/

// Emergency safe placeholder.
// The graphic editor frontend is temporarily disabled so the Odoo backend can load safely again.

import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";

class GroundliftGraphicsDisabledEditor extends Component {
    static template = xml`
        <div class="p-4">
            <h3>Grafikeditor vorübergehend deaktiviert</h3>
            <p>Der Rendering-Fix wurde zurückgenommen, damit Odoo wieder stabil lädt.</p>
        </div>`;
}

registry.category("actions").add("groundlift_graphics.GraphicsEditor", GroundliftGraphicsDisabledEditor);
