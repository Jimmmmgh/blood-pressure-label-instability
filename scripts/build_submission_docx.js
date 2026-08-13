const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  LineNumberRestartFormat,
  PageNumber,
  PageOrientation,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  VerticalAlign,
  WidthType,
} = require("docx");


const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "manuscript", "jic", "word");
fs.mkdirSync(OUT, { recursive: true });

const A4 = { width: 11906, height: 16838 };
const MARGIN = 1440;
const PORTRAIT_CONTENT = A4.width - 2 * MARGIN;
const LANDSCAPE_CONTENT = A4.height - 2 * MARGIN;
const NAVY = "17365D";
const BLUE = "2E75B6";
const ORANGE = "E85D04";
const GREY = "D9E1F2";
const LIGHT_GREY = "E7E6E6";
const RED = "C00000";


function typographic(text) {
  return text
    .replace(/\+\/-/g, "±")
    .replace(/>=/g, "≥")
    .replace(/<=/g, "≤")
    .replace(/\b(\d+(?:\.\d+)?)%-(\d+(?:\.\d+)?)%\b/g, "$1%–$2%")
    .replace(/\b(\d+)-(\d+)\b/g, "$1–$2")
    .replace(/'s\b/g, "’s")
    .replace(/\bNo-Go\b/g, "No-Go");
}


function inlineRuns(text, base = {}) {
  text = typographic(text);
  const runs = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[A-Z][A-Z0-9 /,;:\-'.()]+(?:REQUIRED|CONFIRMATION|REVIEW)[^\]]*\])/g;
  let pos = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > pos) runs.push(new TextRun({ text: text.slice(pos, match.index), ...base }));
    const token = match[0];
    if (token.startsWith("**")) {
      runs.push(new TextRun({ text: token.slice(2, -2), bold: true, ...base }));
    } else if (token.startsWith("`")) {
      runs.push(new TextRun({ text: token.slice(1, -1), font: "Consolas", size: 18, ...base }));
    } else {
      runs.push(new TextRun({ text: token, bold: true, color: RED, ...base }));
    }
    pos = match.index + token.length;
  }
  if (pos < text.length) runs.push(new TextRun({ text: text.slice(pos), ...base }));
  return runs.length ? runs : [new TextRun({ text, ...base })];
}


function tableWidths(data, totalWidth) {
  const columns = data[0].length;
  const raw = Array.from({ length: columns }, (_, i) => {
    const longest = Math.max(...data.map((row) => String(row[i] || "").length));
    return Math.max(6, Math.min(34, longest));
  });
  const minimum = columns >= 9 ? 800 : columns >= 7 ? 950 : 1200;
  let widths = raw.map((w) => Math.max(minimum, Math.floor((totalWidth * w) / raw.reduce((a, b) => a + b, 0))));
  const sum = widths.reduce((a, b) => a + b, 0);
  if (sum !== totalWidth) {
    const scale = totalWidth / sum;
    widths = widths.map((w) => Math.floor(w * scale));
    widths[widths.length - 1] += totalWidth - widths.reduce((a, b) => a + b, 0);
  }
  return widths;
}


function makeTable(data, totalWidth, plainTables = false) {
  const cols = data[0].length;
  const widths = tableWidths(data, totalWidth);
  const fontSize = cols >= 10 ? 12 : cols >= 8 ? 13 : cols >= 6 ? 14 : 16;
  const border = { style: BorderStyle.SINGLE, size: 2, color: "A6A6A6" };
  const borders = { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border };
  const tableRows = data.map((row, rowIndex) => new TableRow({
    tableHeader: rowIndex === 0,
    cantSplit: true,
    children: row.map((cell, colIndex) => new TableCell({
      width: { size: widths[colIndex], type: WidthType.DXA },
      verticalAlign: VerticalAlign.CENTER,
      borders,
      shading: !plainTables && rowIndex === 0 ? { fill: GREY, type: ShadingType.CLEAR } : undefined,
      margins: { top: 55, bottom: 55, left: 65, right: 65 },
      children: [new Paragraph({
        alignment: colIndex === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
        spacing: { before: 0, after: 0, line: 200 },
        children: inlineRuns(String(cell || ""), { size: fontSize, bold: rowIndex === 0 }),
      })],
    })),
  }));
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: tableRows,
  });
}


function parseTable(lines, start) {
  const raw = [];
  let index = start;
  while (index < lines.length && lines[index].trim().startsWith("|")) {
    const cells = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((x) => x.trim());
    if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) raw.push(cells);
    index += 1;
  }
  return { data: raw, next: index };
}


function paragraph(text, options = {}) {
  return new Paragraph({
    alignment: options.alignment || AlignmentType.JUSTIFIED,
    spacing: options.spacing || { before: 0, after: 120, line: 360 },
    keepNext: options.keepNext || false,
    pageBreakBefore: options.pageBreakBefore || false,
    indent: options.indent,
    numbering: options.numbering,
    border: options.border,
    children: inlineRuns(text, options.run || {}),
  });
}


function parseMarkdown(markdown, config) {
  const lines = markdown.replace(/\r/g, "").split("\n");
  const blocks = [];
  let numberList = 0;
  let inCode = false;
  let lastTableWide = false;
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      inCode = !inCode;
      i += 1;
      continue;
    }
    if (inCode) {
      blocks.push({ node: paragraph(trimmed, { alignment: AlignmentType.LEFT, spacing: { after: 0, line: 240 }, run: { font: "Consolas", size: 18, color: trimmed.includes("false") ? RED : NAVY } }), wide: false });
      i += 1;
      continue;
    }
    if (!trimmed || trimmed === "---") {
      i += 1;
      continue;
    }
    if (trimmed.startsWith("|")) {
      const parsed = parseTable(lines, i);
      const wide = parsed.data[0].length >= config.wideColumns;
      blocks.push({ kind: "table", data: parsed.data, wide });
      lastTableWide = wide;
      i = parsed.next;
      continue;
    }
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      if (level === 1) {
        blocks.push({ node: new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 0, after: config.compact ? 180 : 360 },
          children: inlineRuns(text, { bold: true, size: config.compact ? 28 : 34, color: config.plainJournal ? "000000" : NAVY }),
        }), wide: false });
      } else {
        const isPageStart = config.pageBreakHeadings.includes(text);
        blocks.push({ node: new Paragraph({
          heading: level === 2 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
          pageBreakBefore: isPageStart,
          keepNext: true,
          children: inlineRuns(text),
        }), wide: false });
      }
      i += 1;
      continue;
    }
    const bullet = trimmed.match(/^-\s+(.+)$/);
    if (bullet) {
      blocks.push({ node: paragraph(bullet[1], { alignment: AlignmentType.LEFT, numbering: { reference: "bullets", level: 0 }, spacing: config.compact ? { after: 20, line: 230 } : { after: 80, line: 320 }, run: config.compact ? { size: 20 } : {} }), wide: false });
      i += 1;
      continue;
    }
    const numbered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (numbered) {
      if (i === 0 || !lines[i - 1].trim().match(/^\d+\.\s+/)) numberList += 1;
      blocks.push({ node: paragraph(numbered[1], { alignment: AlignmentType.LEFT, numbering: { reference: `numbers-${numberList}`, level: 0 }, spacing: config.compact ? { after: 20, line: 230 } : { after: 80, line: 320 }, run: config.compact ? { size: 20 } : {} }), wide: false });
      i += 1;
      continue;
    }
    if (/^\*\*Table \d+\.[^*]+\*\*$/.test(trimmed)) {
      let next = i + 1;
      while (next < lines.length && !lines[next].trim()) next += 1;
      const nextTable = next < lines.length && lines[next].trim().startsWith("|") ? parseTable(lines, next) : null;
      const wide = nextTable ? nextTable.data[0].length >= config.wideColumns : false;
      blocks.push({ node: paragraph(trimmed, { alignment: AlignmentType.LEFT, keepNext: true }), wide });
      i += 1;
      continue;
    }
    if (/^\*\*Table \d+ legend\.\*\*/.test(trimmed)) {
      blocks.push({ node: paragraph(trimmed, { alignment: AlignmentType.LEFT }), wide: lastTableWide });
      i += 1;
      continue;
    }
    if (/^\*\*[^*]+:\*\*/.test(trimmed)) {
      blocks.push({ node: paragraph(trimmed, { alignment: AlignmentType.LEFT, keepNext: true, spacing: config.compact ? { after: 20, line: 230 } : undefined, run: config.compact ? { size: 20 } : {} }), wide: false });
      i += 1;
      continue;
    }
    blocks.push({ node: paragraph(trimmed, config.compact ? { spacing: { after: 30, line: 230 }, run: { size: 20 } } : {}), wide: false });
    i += 1;
  }
  return { blocks, numberList };
}


function sectionProperties(landscape, lineNumbers, compact) {
  const margin = compact ? 1080 : MARGIN;
  return {
    page: {
      size: { width: A4.width, height: A4.height, orientation: landscape ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
      margin: { top: margin, right: margin, bottom: margin, left: margin, header: 0, footer: 540 },
    },
    lineNumbers: lineNumbers ? { countBy: 1, start: 1, restart: LineNumberRestartFormat.CONTINUOUS, distance: 360 } : undefined,
  };
}


function footerOnly() {
  return {
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], size: 16 })],
      })] }),
    },
  };
}


function makeSections(blocks, config) {
  const sections = [];
  let currentWide = config.landscapeAll;
  let children = [];
  const flush = () => {
    if (!children.length) return;
    const hf = footerOnly();
    sections.push({
      properties: sectionProperties(currentWide, config.lineNumbers, config.compact),
      footers: hf.footers,
      children,
    });
    children = [];
  };
  for (const block of blocks) {
    const desiredWide = config.landscapeAll || Boolean(block.wide);
    if (desiredWide !== currentWide && children.length) flush();
    currentWide = desiredWide;
    if (block.kind === "table") {
      children.push(makeTable(block.data, currentWide ? LANDSCAPE_CONTENT : PORTRAIT_CONTENT, config.plainTables));
      children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
    } else {
      children.push(block.node);
    }
  }
  flush();
  return sections;
}


function styles(plainJournal = false) {
  return {
    default: { document: { run: { font: "Arial", size: 22, color: "000000" }, paragraph: { spacing: { after: 120, line: 360 } } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Arial", size: 28, bold: true, color: plainJournal ? "000000" : NAVY },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0, keepNext: true },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Arial", size: 24, bold: true, color: plainJournal ? "000000" : BLUE },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1, keepNext: true },
      },
    ],
  };
}


function numbering(numberList) {
  const config = [{
    reference: "bullets",
    levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
  }];
  for (let i = 1; i <= Math.max(1, numberList); i += 1) {
    config.push({
      reference: `numbers-${i}`,
      levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
    });
  }
  return { config };
}


function figureBlocks(markdown) {
  const files = [
    [1, "Figure_1_graphical_abstract.png"],
    [2, "Figure_2_measurement_instability.png"],
    [3, "Figure_3_robustness.png"],
    [4, "Figure_4_outcome_sensitivity.png"],
    [5, "Figure_5_vitaldb_waveform_no_go.png"],
  ];
  const lines = markdown.replace(/\r/g, "").split("\n");
  const legends = new Map();
  for (let i = 0; i < lines.length; i += 1) {
    const match = lines[i].trim().match(/^### Figure (\d+)\.\s+(.+)$/);
    if (!match) continue;
    let next = i + 1;
    while (next < lines.length && !lines[next].trim()) next += 1;
    legends.set(Number(match[1]), `Figure ${match[1]}. ${match[2]}. ${lines[next].trim()}`);
  }
  const blocks = [];
  for (const [number, file] of files) {
    const full = path.join(ROOT, "figures", file);
    const isWide = file.startsWith("Figure_1");
    const width = isWide ? 860 : 660;
    const sourceRatio = isWide ? 716 / 2195 : file.includes("Figure_2") ? 3310 / 4389 : file.includes("Figure_3") ? 3070 / 4384 : file.includes("Figure_4") ? 3069 / 4389 : 2590 / 4389;
    blocks.push({ node: new Paragraph({
      alignment: AlignmentType.CENTER,
      pageBreakBefore: true,
      keepNext: true,
      children: [new ImageRun({
        type: "png",
        data: fs.readFileSync(full),
        transformation: { width, height: Math.round(width * sourceRatio) },
        altText: { title: `Figure ${number}`, description: legends.get(number) || `Figure ${number}`, name: file },
      })],
    }), wide: true });
    blocks.push({ node: paragraph(legends.get(number) || `Figure ${number}.`, {
      alignment: AlignmentType.JUSTIFIED,
      spacing: { before: 80, after: 120, line: 240 },
      run: { size: 18 },
    }), wide: true });
  }
  return blocks;
}


async function build(markdownFile, outputFile, config) {
  const md = fs.readFileSync(markdownFile, "utf8");
  const baseMd = config.includeFigures
    ? md.replace(/\n## Figure legends[\s\S]*?(?=\n## References)/, "").trimEnd()
    : md;
  const parsed = parseMarkdown(baseMd, config);
  const blocks = config.includeFigures ? parsed.blocks.concat(figureBlocks(md)) : parsed.blocks;
  const doc = new Document({
    creator: "Manuscript production workflow",
    title: config.title,
    description: config.description,
    styles: styles(config.plainJournal),
    numbering: numbering(parsed.numberList),
    sections: makeSections(blocks, config),
  });
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputFile, buffer);
  console.log(`Wrote ${outputFile}`);
}


async function main() {
  const common = {
    wideColumns: 7,
    pageBreakHeadings: [],
    landscapeAll: false,
    lineNumbers: true,
    includeFigures: false,
    plainJournal: true,
    plainTables: true,
    title: "Measurement-source instability of ICU hypotension phenotypes",
    description: "Submission manuscript for Journal of Intensive Care",
  };
  await build(
    path.join(ROOT, "manuscript", "MANUSCRIPT.md"),
    path.join(OUT, "Manuscript_Journal_of_Intensive_Care.docx"),
    common,
  );
  await build(
    path.join(ROOT, "manuscript", "MANUSCRIPT.md"),
    path.join(OUT, "Manuscript_JIC_Review_Copy_with_Figures.docx"),
    { ...common, includeFigures: true, title: "Measurement-source instability of ICU hypotension phenotypes - review copy" },
  );
  await build(
    path.join(ROOT, "manuscript", "SUPPLEMENTARY_MATERIAL.md"),
    path.join(OUT, "Additional_File_1_Supplementary_Material.docx"),
    {
      wideColumns: 6,
      pageBreakHeadings: [],
      landscapeAll: true,
      lineNumbers: false,
      includeFigures: false,
      plainJournal: true,
      plainTables: true,
      title: "Supplementary material",
      description: "Supplementary material for Journal of Intensive Care submission",
    },
  );
  await build(
    path.join(ROOT, "manuscript", "jic", "COVER_LETTER_JIC.md"),
    path.join(OUT, "Cover_Letter_JIC.docx"),
    {
      wideColumns: 7,
      pageBreakHeadings: [],
      landscapeAll: false,
      lineNumbers: false,
      includeFigures: false,
      plainJournal: true,
      plainTables: true,
      title: "Cover letter",
      description: "Cover letter for Journal of Intensive Care",
      compact: true,
    },
  );
}


main().catch((error) => {
  console.error(error);
  process.exit(1);
});
