// 酒店投资计算器 — 代码混淆构建脚本
// 用法: node build-obfuscated.js
const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');

const SRC = path.join(__dirname, 'index.html');
const OUT = path.join(__dirname, 'dist', 'index.html');

console.log('🔒 酒店投资计算器 — 代码混淆构建');

// 1. 读取原始 HTML
const html = fs.readFileSync(SRC, 'utf-8');
console.log(`  原始文件: ${(html.length / 1024).toFixed(1)} KB`);

// 2. 提取主 JS 块（<script> 内部无 src 属性的那个）
//    跳过第一个小脚本 (recalcInvestment)
const scriptRegex = /<script>\s*(\/\/ ={60,}\s*\/\/ 酒店类型模式[\s\S]*?)<\/script>/;
const match = html.match(scriptRegex);
if (!match) {
  console.error('❌ 找不到主 JS 脚本块');
  process.exit(1);
}
const fullMatch = match[0];
const jsCode = match[1];

console.log(`  提取 JS: ${(jsCode.length / 1024).toFixed(1)} KB`);

// 3. 强力混淆
console.log('  正在混淆...');
const startTime = Date.now();
const result = JavaScriptObfuscator.obfuscate(jsCode, {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.5,
  deadCodeInjection: false,          // 死代码注入太大，不开
  debugProtection: false,
  disableConsoleOutput: false,
  identifierNamesGenerator: 'hexadecimal',
  log: false,
  numbersToExpressions: true,
  renameGlobals: false,
  selfDefending: false,
  simplify: true,
  splitStrings: true,
  splitStringsChunkLength: 20,
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayCallsTransformThreshold: 0.5,
  stringArrayEncoding: ['base64'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 1,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersType: 'function',
  stringArrayThreshold: 0.5,
  transformObjectKeys: true,
  unicodeEscapeSequence: false
});

const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
console.log(`  混淆完成: ${elapsed}s`);
console.log(`  混淆后 JS: ${(result.getObfuscatedCode().length / 1024).toFixed(1)} KB`);

// 4. 替换 HTML 中的 JS
const obfuscatedBlock = '<script>\n' + result.getObfuscatedCode() + '\n</script>';
const obfuscatedHtml = html.replace(fullMatch, obfuscatedBlock);

// 5. 压缩 HTML（去掉多余空行、注释中的空格等）
const minifiedHtml = obfuscatedHtml
  .replace(/<!--[\s\S]*?-->/g, (comment) => {
    // 保留注释但去掉多余空格
    return comment.replace(/\s+/g, ' ').trim();
  })
  .replace(/\n\s*\n/g, '\n');

// 6. 输出
if (!fs.existsSync(path.dirname(OUT))) {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
}
fs.writeFileSync(OUT, minifiedHtml, 'utf-8');
console.log(`  输出文件: ${(minifiedHtml.length / 1024).toFixed(1)} KB → ${OUT}`);
console.log('✅ 混淆构建完成!');
