import fs from "node:fs/promises";
import process from "node:process";
import readline from "node:readline";
import zlib from "node:zlib";

const DEFAULT_DATA_URL =
  "https://yang-global-macro-ai-monitor.streamlit.app/app/static/workbuddy/latest.json";
const DATA_URL = process.env.RADAR_DATA_URL || DEFAULT_DATA_URL;
const DATA_FILE = process.env.RADAR_DATA_FILE || "";
const CACHE_MS = 60_000;
let cache = { at: 0, payload: null };

const tools = [
  {
    name: "get_daily_brief",
    description:
      "获取当天A股盘前摘要。09:00返回海外候选池，09:27后返回集合竞价定价复核。可传入网站链接中的watch参数以使用该用户的自选股。",
    inputSchema: {
      type: "object",
      properties: {
        watchlist_token: {
          type: "string",
          description: "网站URL中watch=后面的完整值；不传则使用默认自选股。",
        },
        limit: {
          type: "integer",
          minimum: 1,
          maximum: 10,
          default: 3,
          description: "最多返回多少项重点信号。",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "analyze_watchlist",
    description:
      "根据用户直接提供的自选股清单，检查隔夜新闻、海外价格确认和A股集合竞价状态。不会修改网站自选股。",
    inputSchema: {
      type: "object",
      required: ["watchlist"],
      properties: {
        watchlist: {
          type: "array",
          minItems: 1,
          maxItems: 30,
          items: {
            type: "object",
            required: ["ticker"],
            properties: {
              ticker: { type: "string", description: "6位A股代码或带交易所后缀的代码。" },
              name: { type: "string" },
              theme: { type: "string", description: "网站配置中的映射主题。" },
              relation: { type: "string", enum: ["同向", "反向", "需判断"] },
              overseas_assets: { type: "array", items: { type: "string" } },
              keywords: { type: "array", items: { type: "string" } },
            },
            additionalProperties: false,
          },
        },
        limit: { type: "integer", minimum: 1, maximum: 10, default: 3 },
      },
      additionalProperties: false,
    },
  },
  {
    name: "analyze_stock",
    description:
      "分析一只A股是否受到当天隔夜事件影响，并返回证据、传导路径和竞价定价状态。",
    inputSchema: {
      type: "object",
      required: ["ticker"],
      properties: {
        ticker: { type: "string" },
        name: { type: "string" },
        theme: { type: "string" },
        relation: { type: "string", enum: ["同向", "反向", "需判断"] },
        overseas_assets: { type: "array", items: { type: "string" } },
        keywords: { type: "array", items: { type: "string" } },
      },
      additionalProperties: false,
    },
  },
];

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeTicker(value = "") {
  const raw = String(value).trim().toUpperCase().replaceAll(" ", "");
  if (/\.(SS|SZ|BJ)$/.test(raw)) return raw;
  const digits = raw.replace(/\D/g, "");
  if (digits.length !== 6) return raw;
  if (/^(4|8|92)/.test(digits)) return `${digits}.BJ`;
  if (/^(5|6|9)/.test(digits)) return `${digits}.SS`;
  return `${digits}.SZ`;
}

function splitTokens(value) {
  if (Array.isArray(value)) return value.map(String).map((x) => x.trim()).filter(Boolean);
  return String(value || "")
    .replaceAll("，", ",")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function normalizeWatchlist(rows = []) {
  const clean = [];
  const seen = new Set();
  for (const row of rows) {
    const ticker = normalizeTicker(row.ticker || row.code || "");
    if (!ticker || seen.has(ticker)) continue;
    const relation = ["同向", "反向", "需判断"].includes(row.relation) ? row.relation : "需判断";
    clean.push({
      ticker,
      name: String(row.name || ticker).trim(),
      theme: String(row.theme || "待分类").trim(),
      relation,
      overseas_assets: splitTokens(row.overseas_assets),
      keywords: splitTokens(row.keywords),
    });
    seen.add(ticker);
    if (clean.length >= 30) break;
  }
  return clean;
}

function decodeWatchlist(token, fallback) {
  if (!token) return normalizeWatchlist(fallback);
  try {
    const buffer = Buffer.from(String(token), "base64url");
    const rows = JSON.parse(zlib.inflateSync(buffer).toString("utf8"));
    const clean = normalizeWatchlist(rows);
    return clean.length ? clean : normalizeWatchlist(fallback);
  } catch {
    throw new Error("自选股链接中的watch参数无法解析，请复制完整链接后重试。");
  }
}

function newsText(item) {
  return `${item.title || ""} ${item.source || ""}`.toLowerCase();
}

function directMatch(stock, item) {
  const text = newsText(item);
  const needles = [stock.name, stock.ticker.split(".")[0], ...(stock.keywords || [])];
  return needles.some((needle) => String(needle || "").trim().length >= 2 && text.includes(String(needle).trim().toLowerCase()));
}

function themeMatch(stock, item) {
  return stock.theme && stock.theme !== "待分类" && (item.themes || []).includes(stock.theme);
}

function assetMoves(keys, market) {
  return (keys || [])
    .map((key) => {
      const item = market[key] || {};
      const move = finite(item.change_pct);
      return move === null ? null : { key, name: item.name || key, move: Math.round(move * 100) / 100 };
    })
    .filter(Boolean)
    .sort((a, b) => Math.abs(b.move) - Math.abs(a.move));
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function priceConfirmation(keys, market) {
  const moves = assetMoves(keys, market);
  const values = moves.map((row) => row.move);
  const med = median(values);
  const strongest = moves[0] || null;
  const confirmed = Boolean(
    strongest && (Math.abs(strongest.move) >= 2 || (values.length >= 2 && med !== null && Math.abs(med) >= 1)),
  );
  const anchor = med !== null && med !== 0 ? med : strongest?.move;
  return {
    confirmed,
    direction: anchor > 0 ? "上涨" : anchor < 0 ? "下跌" : "中性",
    median: med,
    strongest,
    moves,
  };
}

function marketItemForStock(stock, market) {
  return Object.values(market).find((item) => item.ticker === stock.ticker) || {};
}

function targetsForTheme(theme, item, map, watchlist, market) {
  const direct = watchlist.filter((stock) => directMatch(stock, item));
  const thematic = watchlist.filter((stock) => stock.theme === theme && !direct.includes(stock));
  const targets = [...direct, ...thematic].map((stock) => ({
    ticker: stock.ticker,
    name: stock.name,
    source: "自选股",
    role: "自选",
    relation: stock.relation,
    beta: stock.relation === "同向" ? 1 : stock.relation === "反向" ? -1 : 0,
  }));
  for (const key of map.a_share_assets || []) {
    const marketItem = market[key] || {};
    const ticker = marketItem.ticker || key;
    const name = marketItem.name || key;
    if (!targets.some((row) => row.ticker === ticker || row.name === name)) {
      const beta = map.target_beta?.[key] ?? 1;
      targets.push({
        ticker,
        name,
        source: "主题映射",
        role: map.target_roles?.[key] || "",
        relation: beta === 1 ? "同向" : beta === -1 ? "反向" : "需判断",
        beta,
      });
    }
  }
  return targets.slice(0, 8);
}

function evaluateAuction(signal, target, quote) {
  if (!quote || quote.status !== "ok") {
    return { status: "竞价数据缺失", gap_pct: null, reason: "未取得有效集合竞价价格。", source: "" };
  }
  const gap = finite(quote.gap_pct);
  if (gap === null) return { status: "竞价数据缺失", gap_pct: null, reason: "集合竞价涨跌幅无法计算。", source: quote.source || "" };
  if (signal.category !== "海外已验证") {
    return { status: "等待海外确认", gap_pct: gap, reason: "新闻尚未获得海外价格确认。", source: quote.source || "" };
  }
  const beta = Number(target.beta || 0);
  if (!["上涨", "下跌"].includes(signal.price_direction) || beta === 0) {
    return { status: "方向需人工判断", gap_pct: gap, reason: "需要先核对公司暴露。", source: quote.source || "" };
  }
  const effective = gap * (signal.price_direction === "上涨" ? 1 : -1) * beta;
  const overseasAbs = Math.max(0, ...(signal.price_moves || []).map((row) => Math.abs(finite(row.move) || 0)));
  const pricedCutoff = Math.max(1, overseasAbs * 0.45);
  const excessiveCutoff = Math.max(3, overseasAbs * 1.25);
  let status;
  let reason;
  if (effective >= excessiveCutoff) {
    status = "过度定价/追高风险";
    reason = `竞价有效反应 ${effective.toFixed(2)}%，超过高位阈值 ${excessiveCutoff.toFixed(2)}%。`;
  } else if (effective >= pricedCutoff) {
    status = "基本定价";
    reason = `竞价有效反应 ${effective.toFixed(2)}%，达到基本定价阈值 ${pricedCutoff.toFixed(2)}%。`;
  } else if (effective <= -0.5) {
    status = "A股不确认";
    reason = `竞价有效反应 ${effective.toFixed(2)}%，方向与海外信号相反。`;
  } else {
    status = "仍有预期差";
    reason = `竞价有效反应 ${effective.toFixed(2)}%，未达到基本定价阈值 ${pricedCutoff.toFixed(2)}%。`;
  }
  return { status, gap_pct: gap, effective_gap: effective, reason, source: quote.source || "" };
}

function buildSignals(payload, watchlist) {
  const { market = {}, news = [], mapping = {}, auction_quotes: quotes = {} } = payload.context || {};
  const signals = [];
  for (const item of news) {
    const evidence = Number(item.evidence_score || 0);
    if (evidence < 70) continue;
    const theme = (item.themes || []).find((value) => mapping[value]);
    if (!theme) continue;
    const map = mapping[theme];
    const confirmation = priceConfirmation(map.global_assets || [], market);
    const targets = targetsForTheme(theme, item, map, watchlist, market);
    if (!targets.length) continue;
    const direct = watchlist.some((stock) => directMatch(stock, item));
    const relevant = direct || watchlist.some((stock) => stock.theme === theme);
    const strongest = confirmation.strongest;
    const moveScore = strongest ? Math.min((Math.abs(strongest.move) / 4) * 35, 35) : 0;
    const signal = {
      category: confirmation.confirmed ? "海外已验证" : "传导待验证",
      priority: Math.round(Math.min(100, evidence * 0.45 + moveScore + (direct ? 20 : relevant ? 14 : 7))),
      theme,
      title: item.title || "",
      url: item.url || "",
      source: item.source || "",
      published: item.published || "",
      evidence_score: evidence,
      evidence_label: item.evidence_label || "",
      price_text: strongest ? `${strongest.name} ${strongest.move >= 0 ? "+" : ""}${strongest.move.toFixed(2)}%` : "相关海外代理暂无有效价格",
      price_direction: confirmation.direction,
      price_moves: confirmation.moves.slice(0, 4),
      watchlist_relevant: relevant,
      transmission: map.logic || "待核实传导链",
      direction_note: map.direction_note || "必须核对A股标的是受益端还是受损端。",
      next_check: confirmation.confirmed ? "集合竞价强弱、开盘量价与板块扩散" : "先核对原始事实，再等待海外价格或A股集合竞价确认",
      invalidation: map.invalidation || "若后续价格与基本面均不确认，应降低信号权重。",
      targets,
    };
    signal.targets = targets.map((target) => ({
      ...target,
      auction: payload.stage === "auction_review"
        ? evaluateAuction(signal, target, quotes[target.ticker])
        : { status: "等待09:27竞价", gap_pct: null, reason: "09:00先形成海外候选池，09:27后再判断是否已被A股定价。", source: "" },
    }));
    signals.push(signal);
  }
  const statusRank = { "仍有预期差": 0, "方向需人工判断": 1, "A股不确认": 2, "基本定价": 3, "过度定价/追高风险": 4, "竞价数据缺失": 5, "等待海外确认": 6 };
  return signals.sort((a, b) => {
    if ((a.category === "海外已验证") !== (b.category === "海外已验证")) return a.category === "海外已验证" ? -1 : 1;
    const aRank = Math.min(7, ...a.targets.map((x) => statusRank[x.auction.status] ?? 7));
    const bRank = Math.min(7, ...b.targets.map((x) => statusRank[x.auction.status] ?? 7));
    if (Object.keys(quotes).length && aRank !== bRank) return aRank - bRank;
    if (a.watchlist_relevant !== b.watchlist_relevant) return a.watchlist_relevant ? -1 : 1;
    return b.priority - a.priority;
  });
}

function buildAlerts(payload, watchlist, signals) {
  const { market = {}, news = [], mapping = {} } = payload.context || {};
  const reliable = news.filter((item) => Number(item.evidence_score || 0) >= 70);
  const byTicker = new Map();
  for (const signal of signals.filter((row) => row.category === "海外已验证")) {
    for (const target of signal.targets) {
      if (!byTicker.has(target.ticker)) byTicker.set(target.ticker, { ...target.auction, signal_title: signal.title, signal_priority: signal.priority });
    }
  }
  return watchlist
    .map((stock) => {
      const direct = reliable.filter((item) => directMatch(stock, item));
      const thematic = reliable.filter((item) => themeMatch(stock, item) && !direct.includes(item));
      const map = mapping[stock.theme] || {};
      const confirmation = priceConfirmation(stock.overseas_assets.length ? stock.overseas_assets : map.global_assets || [], market);
      const own = marketItemForStock(stock, market);
      const level = direct.length || (confirmation.confirmed && (thematic.length || Object.keys(map).length)) ? "重点异动" : thematic.length || confirmation.moves.length ? "需要关注" : "暂无异动";
      const reasons = [];
      if (direct.length) reasons.push(`发现${direct.length}条直接相关新闻`);
      else if (thematic.length) reasons.push(`发现${thematic.length}条${stock.theme}可靠新闻`);
      if (confirmation.strongest) reasons.push(`海外代理 ${confirmation.strongest.name} ${confirmation.strongest.move >= 0 ? "+" : ""}${confirmation.strongest.move.toFixed(2)}%`);
      if (!reasons.length) reasons.push("未发现可靠新闻或显著海外代理波动");
      const headline = direct[0] || thematic[0] || {};
      return {
        ticker: stock.ticker,
        name: stock.name,
        theme: stock.theme,
        level,
        reason: reasons.join("；"),
        headline: headline.title || "",
        source: headline.source || "",
        news_url: headline.url || "",
        overseas_direction: confirmation.direction,
        overseas_moves: confirmation.moves.slice(0, 4),
        previous_close: finite(own.last),
        previous_day_move: finite(own.change_pct),
        auction: byTicker.get(stock.ticker) || {
          status: Object.keys(payload.context?.auction_quotes || {}).length ? "无对应海外验证信号" : "等待09:27竞价",
          gap_pct: null,
          reason: Object.keys(payload.context?.auction_quotes || {}).length ? "当前没有可用于第二阶段判断的海外已验证事件。" : "09:00先形成海外候选池。",
        },
      };
    })
    .sort((a, b) => ({ "重点异动": 0, "需要关注": 1, "暂无异动": 2 })[a.level] - ({ "重点异动": 0, "需要关注": 1, "暂无异动": 2 })[b.level]);
}

async function loadPayload() {
  if (cache.payload && Date.now() - cache.at < CACHE_MS) return cache.payload;
  let payload;
  if (DATA_FILE) {
    payload = JSON.parse(await fs.readFile(DATA_FILE, "utf8"));
  } else {
    const response = await fetch(DATA_URL, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(15_000) });
    if (!response.ok) throw new Error(`盘前数据源返回HTTP ${response.status}`);
    payload = await response.json();
  }
  if (payload.schema_version !== "1.0" || !payload.context) throw new Error("盘前数据格式不受支持");
  cache = { at: Date.now(), payload };
  return payload;
}

function resultFor(payload, watchlist, limit = 3) {
  const signals = buildSignals(payload, watchlist);
  const alerts = buildAlerts(payload, watchlist, signals);
  const relevant = signals.filter((row) => row.watchlist_relevant);
  const top = (relevant.length ? relevant : signals).slice(0, Math.max(1, Math.min(Number(limit) || 3, 10)));
  return {
    trade_date: payload.trade_date,
    generated_at: payload.generated_at,
    stage: payload.stage,
    stage_label: payload.stage_label,
    data_freshness_note: payload.stage === "auction_review" ? "已取得当日集合竞价复核" : "当前仅为09:00候选，尚未进行当日集合竞价复核",
    watchlist_count: watchlist.length,
    watchlist_alerts: alerts,
    top_signals: top,
    site_url: payload.site_url,
    disclaimer: payload.disclaimer,
  };
}

async function callTool(name, args) {
  const payload = await loadPayload();
  const defaults = payload.context.default_watchlist || [];
  if (name === "get_daily_brief") {
    const watchlist = decodeWatchlist(args.watchlist_token || "", defaults);
    return resultFor(payload, watchlist, args.limit);
  }
  if (name === "analyze_watchlist") {
    const watchlist = normalizeWatchlist(args.watchlist || []);
    if (!watchlist.length) throw new Error("至少需要一只有效的A股股票代码。");
    return resultFor(payload, watchlist, args.limit);
  }
  if (name === "analyze_stock") {
    const ticker = normalizeTicker(args.ticker);
    const existing = normalizeWatchlist(defaults).find((row) => row.ticker === ticker);
    const stock = normalizeWatchlist([{ ...(existing || {}), ...args, ticker }])[0];
    if (!stock) throw new Error("股票代码无效。");
    const output = resultFor(payload, [stock], 5);
    return { ...output, stock_configuration: stock, configuration_warning: stock.theme === "待分类" ? "缺少映射主题，结果可能仅包含公司名称或代码直接命中的新闻。" : "" };
  }
  throw new Error(`未知工具：${name}`);
}

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

async function handle(message) {
  if (!message || message.jsonrpc !== "2.0" || message.id === undefined) return;
  try {
    if (message.method === "initialize") {
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          protocolVersion: message.params?.protocolVersion || "2025-06-18",
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: "a-share-preopen-radar", version: "1.0.0" },
        },
      });
      return;
    }
    if (message.method === "ping") {
      send({ jsonrpc: "2.0", id: message.id, result: {} });
      return;
    }
    if (message.method === "tools/list") {
      send({ jsonrpc: "2.0", id: message.id, result: { tools } });
      return;
    }
    if (message.method === "tools/call") {
      const data = await callTool(message.params?.name, message.params?.arguments || {});
      send({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
          structuredContent: data,
          isError: false,
        },
      });
      return;
    }
    send({ jsonrpc: "2.0", id: message.id, error: { code: -32601, message: "Method not found" } });
  } catch (error) {
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        content: [{ type: "text", text: `A股盘前机会雷达调用失败：${error.message}` }],
        isError: true,
      },
    });
  }
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    await handle(JSON.parse(line));
  } catch (error) {
    process.stderr.write(`Invalid MCP message: ${error.message}\n`);
  }
}
