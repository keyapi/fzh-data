// Copy this builder into a private runtime folder with the bundled node_modules junction.
import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) throw new Error('Usage: builder input-tables.json output.xlsx');
const outputDir = await fs.realpath(path.dirname(path.resolve(outputPath)));
for (let current = outputDir; ; current = path.dirname(current)) {
  try { await fs.stat(path.join(current, '.git')); throw new Error('Output must stay outside Git'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (current === path.dirname(current)) break;
}
const data = JSON.parse(await fs.readFile(inputPath, 'utf8'));
const workbook = Workbook.create();
for (const source of data.sheets) {
  const sheet = workbook.worksheets.add(source.name);
  sheet.showGridLines = false;
  const cols = source.headers.length;
  const matrix = [source.headers, ...source.rows].map(row => row.map(value => {
    const text = typeof value === 'object' && value !== null ? JSON.stringify(value) : value;
    return typeof text === 'string' && /^[=+@]/.test(text) ? "'" + text : text;
  }));
  sheet.getRangeByIndexes(0, 0, 1, cols).merge();
  sheet.getRange('A1').values = [[source.note]];
  sheet.getRangeByIndexes(0, 0, 1, cols).format = {wrapText: true, rowHeight: 50,
    fill: '#E9F1F7', font: {name: 'Arial', size: 11, color: '#22384D'}};
  const body = sheet.getRangeByIndexes(2, 0, matrix.length, cols);
  body.values = matrix;
  body.format.font = {name: 'Arial', size: 10};
  body.format.columnWidth = 22;
  body.format.rowHeight = 21;
  sheet.getRangeByIndexes(2, 0, 1, cols).format = {fill: '#22384D', font: {bold: true, color: '#FFFFFF'}, rowHeight: 28};
  sheet.getRangeByIndexes(2, 0, matrix.length, 1).format.columnWidth = 42;
  sheet.freezePanes.freezeRows(3);
}
workbook.recalculate();
console.log((await workbook.inspect({kind: 'sheet', include: 'id,name', maxChars: 2000})).ndjson);
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(path.join(outputDir, path.basename(outputPath)));
const preview = await workbook.render({sheetName: '文件覆盖', range: 'A1:H13', scale: 1, format: 'png'});
await fs.writeFile(path.join(outputDir, 'workbook_preview.png'), new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({sheets: data.sheets.length, output: outputPath}));
