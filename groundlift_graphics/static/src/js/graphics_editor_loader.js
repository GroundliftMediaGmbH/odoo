/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";

/*
 * Deliberately tiny and stable.
 * The real renderer runs in /groundlift_graphics/editor/<id> inside an iframe.
 * Therefore a renderer error can no longer break Odoo's global backend assets.
 */
class GroundliftGraphicsEditorLoader extends Component {
    static props = ["action"];
    static template = xml`
        <div class="o_groundlift_graphics_loader" style="height: calc(100vh - 90px); min-height: 720px; background: #151821;">
            <iframe
                t-att-src="src"
                style="width: 100%; height: 100%; border: 0; display: block; background: #151821;"
                allow="clipboard-read; clipboard-write; fullscreen"
            />
        </div>`;

    get src() {
        const posterId = this.props.action?.params?.poster_id;
        return posterId ? `/groundlift_graphics/editor/${posterId}?v=19.0.1.7.1` : "/groundlift_graphics/editor/missing?v=19.0.1.7.1";
    }
}

registry.category("actions").add("groundlift_graphics.GraphicsEditor", GroundliftGraphicsEditorLoader);
