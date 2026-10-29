// Minimal DOM/$ stub harness for so_chain_render (no jsdom dependency).
// usage: node render_harness.js /abs/path/sales_order.js  < scenario.json
// prints: JSON {"html": "..."}
const fs = require('fs');
const vm = require('vm');

const jsPath = process.argv[2];
if (!jsPath) {
    process.stderr.write('missing js path\n');
    process.exit(2);
}

const html = { value: '' };

function chain() {
    const node = {
        length: 0,
        each() { return node; },
        on() { return node; },
        addClass() { return node; },
        removeClass() { return node; },
        attr() { return node; },
        css() { return node; },
        text() { return ''; },
        remove() { return node; },
    };
    return node;
}

const store = {};
const sandbox = {
    console,
    frappe: {
        _: (s) => s,
        utils: {
            escape_html: (s) => String(s == null ? '' : s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
            get_form_link: (dt, name) => '/app/' + dt + '/' + name,
        },
        ui: { form: { on: () => {} }, Dialog: function () {
            return { fields_dict: { html: { $wrapper: chain() } }, show() {} };
        } },
    },
    $: function (selector) {
        const node = chain();
        node.html = function (value) {
            if (typeof value === 'string') html.value = value;
            return node;
        };
        node.find = function () { return chain(); };
        node.children = function () { return chain(); };
        node.eq = function () { return chain(); };
        node.outerWidth = function () { return 100; };
        node.data = function () { return null; };
        node.attr = function () { return ''; };
        node.text = function () { return ''; };
        return node;
    },
    document: {
        getElementById: () => null,
        createElement: () => ({ id: '', textContent: '' }),
        head: { appendChild: () => {} },
    },
    localStorage: {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = v; },
    },
    __: (s) => s,
    window: {},
};
sandbox.globalThis = sandbox;

const code = fs.readFileSync(jsPath, 'utf8');
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: jsPath });

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const data = { sales_order: input.sales_order || 'SO-1', lines: input.lines || [] };
sandbox.so_chain_render(sandbox.$('#box'), data);
process.stdout.write(JSON.stringify({ html: html.value }));
