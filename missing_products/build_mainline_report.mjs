import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, "out");
const files = (await fs.readdir(outDir))
  .filter((name) => name.startsWith("三方一致性审计_") && name.endsWith(".xlsx"))
  .map((name) => ({ name, full: path.join(outDir, name) }));
for (const file of files) file.mtime = (await fs.stat(file.full)).mtimeMs;
files.sort((a, b) => b.mtime - a.mtime);
if (!files.length) throw new Error("未找到三方一致性审计工作簿");

const source = await SpreadsheetFile.importXlsx(await FileBlob.load(files[0].full));
const mappingSheet = source.worksheets.getItem("通途映射全量");
const mappingValues = mappingSheet.getUsedRange(true).values;
const [headers, ...body] = mappingValues;
const rows = body.map((values) => Object.fromEntries(headers.map((key, index) => [key, values[index]])));

const missingSpuSheet = source.worksheets.getItem("赛狐缺SPU");
const missingSpuValues = missingSpuSheet.getUsedRange(true).values;
const [spuHeaders, ...spuBody] = missingSpuValues;
const missingSpus = spuBody.map((values) => Object.fromEntries(spuHeaders.map((key, index) => [key, values[index]])));

const kits = new Set(["TT0031192K0063867", "TT0031102-zuhe-all"]);
for (const row of rows) {
  const exactCount = Number(row["EN精确登记次数"] || 0);
  const candidates = String(row["基码候选产品"] || "").trim();
  row["匹配依据"] = exactCount > 0
    ? "完整通途 SKU 精确匹配 EN 产品 customer_items.ref_code"
    : candidates
      ? "仅去除 -Cover/-Foam 后缀的基码匹配候选，不能视为已登记"
      : "完整 SKU 与基码均无 EN 产品候选";
  row["建议动作"] = exactCount > 0
    ? "无需新增登记；保留现有映射"
    : candidates
      ? "确认属性和适用产品后，登记完整通途 SKU"
      : "暂缓并由运营确认业务归属";
}
const coverRows = rows.filter((row) => String(row["通途SKU"] || "").toLowerCase().endsWith("-cover"));
const foamRows = rows.filter((row) => String(row["通途SKU"] || "").toLowerCase().endsWith("-foam"));
const kitRows = rows.filter((row) => kits.has(String(row["通途SKU"] || "")));
const deferredRows = rows.filter((row) => row["EN登记状态"] !== "已精确登记" && !kits.has(String(row["通途SKU"] || "")));
const duplicateRows = rows.filter((row) => Number(row["EN精确登记次数"] || 0) > 1);
const frameRows = missingSpus.filter((row) => String(row["EN_SPU"] || "").startsWith("ZTGJ5525"));

const reportHeaders = [
  "通途SKU", "清理后SKU", "仓库", "可用库存", "货品名称",
  "分类", "EN登记状态", "EN精确登记次数", "EN精确登记产品", "基码候选产品", "匹配依据",
  "赛狐产品SKU状态", "赛狐已存在SKU", "赛狐缺失SKU",
  "建议动作",
];

const workbook = Workbook.create();
workbook.comments.setSelf({ displayName: "Codex" });

function writeSheet(name, dataRows, selectedHeaders = reportHeaders) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const matrix = [selectedHeaders, ...dataRows.map((row) => selectedHeaders.map((header) => row[header] ?? null))];
  const range = sheet.getRangeByIndexes(0, 0, matrix.length, selectedHeaders.length);
  range.values = matrix;
  const header = sheet.getRangeByIndexes(0, 0, 1, selectedHeaders.length);
  header.format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
  header.format.rowHeight = 32;
  range.format.font = { name: "Microsoft YaHei", size: 10 };
  range.format.borders = { preset: "inside", style: "thin", color: "#D9E2F3" };
  range.format.autofitColumns();
  range.format.autofitRows();
  for (let col = 0; col < selectedHeaders.length; col += 1) {
    const title = selectedHeaders[col];
    const column = sheet.getRangeByIndexes(0, col, matrix.length, 1);
    if (["仓库", "货品名称", "EN精确登记产品", "基码候选产品", "匹配依据", "赛狐已存在SKU", "建议动作"].includes(title)) {
      column.format.columnWidth = 28;
      column.format.wrapText = true;
    } else if (title.includes("SKU") || title.includes("产品")) {
      column.format.columnWidth = 24;
    } else {
      column.format.columnWidth = 14;
    }
  }
  sheet.freezePanes.freezeRows(1);
  sheet.tables.add(range.address, true, `${name.replace(/[^A-Za-z0-9]/g, "") || "Sheet"}${workbook.worksheets.items.length}Table`);
  return sheet;
}

const summary = workbook.worksheets.add("汇总");
summary.showGridLines = false;
summary.getRange("A1:D1").merge();
summary.getRange("A1").values = [["通途有库存 SKU 三方主线补齐报告"]];
summary.getRange("A1:D1").format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 34 };
const summaryRows = [
  ["指标", "数量", "状态", "说明"],
  ["通途有库存 SKU", rows.length, "已对账", "全量输入"],
  ["EN 产品精确登记", rows.filter((row) => row["EN登记状态"] === "已精确登记").length, "已完成", "完整 SKU，含 -Cover/-Foam"],
  ["套件暂缓", kitRows.length, "暂缓", "主线产品一致后再讨论"],
  ["其他非产品项暂缓", deferredRows.length, "暂缓", "已知辅料/杂项"],
  ["皮壳通途 SKU", coverRows.length, coverRows.every((row) => row["EN登记状态"] === "已精确登记") ? "主线完成" : "存在缺口", "必须登记到 EN 产品"],
  ["海绵通途 SKU", foamRows.length, foamRows.every((row) => row["EN登记状态"] === "已精确登记") ? "主线完成" : "存在缺口", "必须登记到 EN 产品"],
  ["一对多历史关系", duplicateRows.length, "保留", "本轮不清理"],
];
summary.getRangeByIndexes(2, 0, summaryRows.length, 4).values = summaryRows;
summary.getRange("A3:D3").format = { fill: "#D9EAF7", font: { bold: true, color: "#1F1F1F" } };
summary.getRange(`A3:D${2 + summaryRows.length}`).format.borders = { preset: "inside", style: "thin", color: "#D9E2F3" };
summary.getRange("A:D").format.font = { name: "Microsoft YaHei", size: 10 };
summary.getRange("A:A").format.columnWidth = 24;
summary.getRange("B:B").format.columnWidth = 12;
summary.getRange("C:C").format.columnWidth = 14;
summary.getRange("D:D").format.columnWidth = 38;
summary.freezePanes.freezeRows(3);

writeSheet("套件暂缓", kitRows);
writeSheet("其他非产品项暂缓", deferredRows);
writeSheet("皮壳通途SKU", coverRows);
writeSheet("海绵通途SKU", foamRows);
writeSheet("主体骨架后续", frameRows, spuHeaders);
writeSheet("一对多历史关系", duplicateRows);
writeSheet("通途映射全量", rows);

const now = new Date();
const stamp = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Shanghai",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hour12: false,
}).format(now).replace(/[- :]/g, "");
const outputPath = path.join(outDir, `通途SKU未在EN产品登记及赛狐状态_${stamp}.xlsx`);
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const preview = await workbook.render({ sheetName: "汇总", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputPath}.png`, new Uint8Array(await preview.arrayBuffer()));
console.log(outputPath);
