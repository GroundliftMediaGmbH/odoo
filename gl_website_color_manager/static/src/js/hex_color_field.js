/** @odoo-module **/

import { Component } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

function normalizeHex(value) {
    let color = String(value || '').trim();
    if (!color) {
        return '';
    }
    if (!color.startsWith('#')) {
        color = '#' + color;
    }
    if (/^#[0-9a-fA-F]{3}$/.test(color)) {
        color = '#' + color.slice(1).split('').map((ch) => ch + ch).join('');
    }
    return color.toLowerCase();
}

export class GlHexColorField extends Component {
    static template = 'gl_website_color_manager.HexColorField';
    static props = { ...standardFieldProps };

    get value() {
        return this.props.record.data[this.props.name] || '';
    }

    get pickerValue() {
        const color = normalizeHex(this.value);
        if (/^#[0-9a-fA-F]{6}$/.test(color)) {
            return color;
        }
        if (/^#[0-9a-fA-F]{8}$/.test(color)) {
            return color.slice(0, 7);
        }
        return '#000000';
    }

    get isEmpty() {
        return !this.value;
    }

    onPickerInput(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }

    onTextInput(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }
}

registry.category('fields').add('gl_hex_color', {
    component: GlHexColorField,
    supportedTypes: ['char'],
});
