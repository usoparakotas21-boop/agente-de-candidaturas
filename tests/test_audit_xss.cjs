const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
test('application company and unknown status stay text', async () => {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; }
    appendChild(child) { this.children.push(child); return child; }
    replaceChildren(...children) { this.children = children; }
    set innerHTML(value) { throw new Error('Untrusted HTML must never be parsed'); }
  }
  const payload = '<img src=x onerror=alert(1)>';
  const meta = new Element('meta');
  const item = new Element('item');
  item.querySelector = selector => selector === 'h2' ? {textContent: 'Job'} : meta;
  const list = {querySelectorAll: () => [item]};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/applications-enhance.js'), 'utf8'), {
    document: {querySelector: () => list, createElement: tag => new Element(tag), createTextNode: text => ({text})},
    fetch: async () => ({json: async () => ({applications: [{job_title:'Job', company:payload, events:[{status:payload}]}]})}),
    MutationObserver: class { observe() {} },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(meta.children[0].children[0].text, payload);
  const event = item.children[0].children[0];
  assert.equal(event.children[0].tag, 'i');
  assert.equal(event.children[1].text, payload);
});
