<template>
  <div class="alerts-page">
    <div class="container">
      <header class="alerts-hero">
        <div class="hero-text">
          <p class="eyebrow"><span class="live-tag">LIVE</span> 实盘监控 · Binance</p>
          <h1>币预警 <span class="brand-dot">.</span></h1>
          <p class="sub">实时价格、日内涨跌幅与极速波动提醒</p>
        </div>
        
        <div class="hero-controls">
          <div class="connection" :class="connectionClass">
            <span class="dot"></span>
            <span class="conn-text">{{ connectionLabel }}</span>
          </div>
          <div class="tz-select-wrapper">
            <select id="tz" v-model="selectedTz" class="fancy-select">
              <option v-for="tz in tzOptions" :key="tz.key" :value="tz.key">{{ tz.label }}</option>
            </select>
          </div>
        </div>
      </header>

      <section class="cards-grid">
        <div v-for="sym in symbols" :key="sym" class="crypto-card">
          <div class="card-content">
            <div class="card-head">
              <div class="symbol-info">
                <span class="symbol-name">{{ sym.replace('USDT', '') }}</span>
                <span class="symbol-pair">/ USDT</span>
              </div>
              <div class="pct-badge" :class="pct(sym) >= 0 ? 'up' : 'down'">
                <span v-if="pct(sym) !== null">{{ pct(sym) > 0 ? '+' : '' }}{{ formatPct(pct(sym)) }}</span>
                <span v-else>--</span>
              </div>
            </div>
            
            <div class="price-section">
              <div class="main-price">
                <span v-if="lastPrice(sym) !== null">{{ formatPrice(lastPrice(sym)) }}</span>
                <span v-else class="loading-text">--</span>
              </div>
              <div class="open-price">
                <span class="label">今开 ({{ currentTzLabel }})</span>
                <span class="val">{{ todayOpen(sym) ?? '--' }}</span>
              </div>
            </div>

            <div class="chart-container">
              <div class="chart" :ref="setChartRef(sym)"></div>
            </div>
          </div>
        </div>
      </section>

      <section class="alerts-section">
        <div class="section-header">
          <div class="header-left">
            <h2>实时预警</h2>
            <div class="pulse-icon"></div>
          </div>
          <span class="count-tag">最近 50 条 · 已去重</span>
        </div>

        <div class="alerts-container">
          <div v-if="alerts.length === 0" class="empty-state">等待波动信号...</div>
          
          <div v-else class="alert-item" v-for="a in alerts" :key="a.id">
            <div class="alert-status-line" :class="a.alert_type"></div>
            
            <div class="alert-top">
              <div class="alert-type-pill" :class="a.alert_type">{{ badge(a.alert_type) }}</div>
              <div class="alert-symbol-info">
                <span class="sym">{{ a.symbol }}</span>
                <span class="mag">{{ formatThreshold(a) }}</span>
                <span class="win">{{ a.window_minutes }}m</span>
              </div>
            </div>

            <div class="alert-flow">
              <div class="flow-info-block">
                <div class="b-label">{{ anchorLabel(a) }}</div>
                <div class="b-date">{{ splitTs(anchorTs(a)).date }}</div>
                <div class="b-time">{{ splitTs(anchorTs(a)).time }}</div>
              </div>

              <!-- 回退并优化的指示器样式 -->
              <div class="flow-price-indicator">
                {{ formatPrice(anchorPrice(a)) }}
              </div>

              <div class="flow-arrow">→</div>

              <div class="flow-info-block">
                <div class="b-label highlight">触发</div>
                <div class="b-date">{{ splitTs(triggerTs(a)).date }}</div>
                <div class="b-time">{{ splitTs(triggerTs(a)).time }}</div>
              </div>

              <div class="flow-price-indicator trigger">
                {{ formatPrice(triggerPrice(a)) }}
              </div>
            </div>

            <div class="alert-footer-fancy">
              <div class="footer-stats">
                <div class="stat-row">
                  <span class="stat-label">实际变动幅度</span>
                  <span class="stat-value" :class="moveFromAnchor(a) < 0 ? 'text-red' : 'text-green'">
                    {{ moveFromAnchor(a) > 0 ? '+' : '' }}{{ pctOrDash(moveFromAnchor(a)) }}
                  </span>
                </div>
                <div class="stat-row">
                  <span class="stat-label">波动监控阈值</span>
                  <span class="stat-value secondary">{{ formatThreshold(a) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const symbols = ['BTCUSDT', 'ETHUSDT']
const maxPoints = 240
const tzOptions = [
  { key: 'utc', label: 'UTC+0', timeZone: 'UTC' },
  { key: 'beijing', label: '北京时间', timeZone: 'Asia/Shanghai' },
  { key: 'us_east', label: '美东 (ET)', timeZone: 'America/New_York' },
  { key: 'us_west', label: '美西 (PT)', timeZone: 'America/Los_Angeles' }
]
const tzOptionMap = Object.fromEntries(tzOptions.map((o) => [o.key, o]))
const selectedTz = ref<string>('utc')
const alerts = reactive<any[]>([])
const lastPrices = reactive<Record<string, number | null>>({ BTCUSDT: null, ETHUSDT: null })
const dayOpens = reactive<any>(
  tzOptions.reduce((acc, tz) => {
    acc[tz.key] = { BTCUSDT: null, ETHUSDT: null }
    return acc
  }, {} as any)
)
const series: any = reactive({ BTCUSDT: [], ETHUSDT: [] })

const charts = new Map<string, any>()
const chartEls = new Map<string, HTMLElement>()
let ws: WebSocket | null = null
let echartsLib: any = null
const connectionState = ref<'connecting' | 'open' | 'closed'>('connecting')
let alertAudio: HTMLAudioElement | null = null
const ALERT_AUDIO_URL = 'https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3'

const connectionLabel = computed(() => connectionState.value === 'open' ? '实时连接' : '连接中...')
const connectionClass = computed(() => ({ live: connectionState.value === 'open', down: connectionState.value === 'closed' }))
const currentTzLabel = computed(() => tzOptionMap[selectedTz.value]?.label ?? 'UTC+0')

function setChartRef(sym: string) {
  return (el: HTMLElement | null) => {
    if (!el) return
    chartEls.set(sym, el)
    if (echartsLib && !charts.has(sym)) {
      initSingleChart(sym, el)
    }
  }
}

function initSingleChart(sym: string, el: HTMLElement) {
  const chart = echartsLib.init(el)
  charts.set(sym, chart)
  chart.setOption(baseOption(sym))
  if (series[sym].length > 0) updateSingleChart(sym)
}

onMounted(async () => {
  await loadEcharts()
  chartEls.forEach((el, sym) => {
    if (!charts.has(sym)) initSingleChart(sym, el)
  })
  if (shouldFetchInitialAlerts()) {
    fetchInitialAlerts()
  }
  connect()
  initAlertAudio()
  playAlertSound()
})

async function loadEcharts() {
  if ((window as any).echarts) {
    echartsLib = (window as any).echarts
    return
  }
  return new Promise((resolve) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'
    script.onload = () => {
      echartsLib = (window as any).echarts
      resolve(true)
    }
    document.head.appendChild(script)
  })
}

function handleMessage(msg: any) {
  if (msg.type === 'snapshot' && msg.data) {
    Object.entries(msg.data).forEach(([sym, payload]: any) => {
      const s = sym.toUpperCase()
      lastPrices[s] = payload.price
      setDayOpens(s, payload.day_open, payload.today_open)
    })
    updateCharts()
  } else if (msg.type === 'price') {
    const s = msg.symbol
    lastPrices[s] = msg.price
    setDayOpens(s, msg.day_open, msg.today_open)
    pushPoint(s, msg.ts, msg.price)
    updateSingleChart(s)
  } else if (msg.type === 'alert') {
    const id = `${msg.symbol}-${msg.alert_type}-${msg.ts}`
    if (!alerts.find(a => a.id === id)) {
      alerts.unshift({ ...msg, id })
      if (alerts.length > 50) alerts.pop()
      playAlertSound()
    }
  }
}

function updateCharts() { symbols.forEach(s => updateSingleChart(s)) }

function updateSingleChart(sym: string) {
  const chart = charts.get(sym)
  if (!chart) return
  const data = series[sym] || []
  const p = pct(sym)
  const color = p === null ? '#cbd5e1' : p >= 0 ? '#16c784' : '#ef4444'
  
  chart.setOption({
    xAxis: { data: data.map((p: any) => fmtTime(p.t)) },
    series: [{
      data: data.map((p: any) => p.v),
      lineStyle: { color: color, width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: color + '33' }, { offset: 1, color: color + '00' }]
        }
      }
    }]
  })
}

function baseOption(sym: string) {
  return {
    tooltip: { 
      show: true, 
      trigger: 'axis',
      confine: true,
      backgroundColor: 'rgba(255, 255, 255, 0.98)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: '#1e293b', fontSize: 12 },
      formatter: (params: any) => {
        const p = params[0];
        const val = typeof p.value === 'number' ? p.value.toFixed(3) : p.value;
        const ts = series[sym]?.[p.dataIndex]?.t;
        const timeLabel = ts ? fmtTimeSeconds(ts) : p.name;
        return `<div style="font-weight:bold;margin-bottom:4px;border-bottom:1px solid #f1f5f9;padding-bottom:2px">${timeLabel}</div>
                <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
                  <span style="color:#64748b">${sym}:</span>
                  <span style="font-weight:800;color:#3b82f6;font-family:var(--main-price-font)">${val}</span>
                </div>`;
      }
    },
    grid: { left: 0, right: 0, top: 10, bottom: 0 },
    xAxis: { type: 'category', show: false, boundaryGap: false },
    yAxis: { type: 'value', scale: true, show: false },
    series: [{ type: 'line', showSymbol: false, smooth: true, animation: false, emphasis: { lineStyle: { width: 3 } } }]
  }
}

function splitTs(ts: number) {
  if (!ts) return { date: '--', time: '--' }
  const tzObj = tzOptionMap[selectedTz.value];
  const tz = tzObj?.timeZone || 'UTC';
  
  let locale = 'en-GB'; 
  if (selectedTz.value === 'beijing') locale = 'zh-CN';
  else if (selectedTz.value === 'us_east' || selectedTz.value === 'us_west') locale = 'en-US';

  const df = new Intl.DateTimeFormat(locale, {
    timeZone: tz,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false
  });

  const parts = df.formatToParts(new Date(ts));
  // 根据 locale 组合日期字符串，确保使用 /
  const dateParts = parts.filter(p => ['year', 'month', 'day'].includes(p.type));
  let dateStr = "";
  if (locale === 'en-US') {
     dateStr = `${dateParts.find(p => p.type==='month')?.value}/${dateParts.find(p => p.type==='day')?.value}/${dateParts.find(p => p.type==='year')?.value}`;
  } else if (locale === 'en-GB') {
     dateStr = `${dateParts.find(p => p.type==='day')?.value}/${dateParts.find(p => p.type==='month')?.value}/${dateParts.find(p => p.type==='year')?.value}`;
  } else {
     dateStr = `${dateParts.find(p => p.type==='year')?.value}/${dateParts.find(p => p.type==='month')?.value}/${dateParts.find(p => p.type==='day')?.value}`;
  }

  const timeStr = parts.filter(p => ['hour', 'minute', 'second'].includes(p.type)).map(p => p.value).join(':');

  return { 
    date: dateStr, 
    time: timeStr 
  }
}

function formatWithTz(ts: number, opts: any) {
  const tzObj = tzOptionMap[selectedTz.value];
  const tz = tzObj?.timeZone || 'UTC';
  let locale = 'en-GB'; 
  if (selectedTz.value === 'beijing') locale = 'zh-CN';
  else if (selectedTz.value === 'us_east' || selectedTz.value === 'us_west') locale = 'en-US';

  try {
    return new Intl.DateTimeFormat(locale, { timeZone: tz, ...opts, hour12: false }).format(new Date(ts));
  } catch (e) {
    return '--';
  }
}

function pushPoint(sym: string, ts: number, price: number) {
  if (!series[sym]) series[sym] = []
  series[sym].push({ t: ts, v: price })
  if (series[sym].length > maxPoints) series[sym].shift()
}

function pct(sym: string) {
  const o = todayOpen(sym); const p = lastPrices[sym]
  return (o && p) ? (p - o) / o : null
}

function todayOpen(sym: string) { return dayOpens[selectedTz.value]?.[sym] }
function lastPrice(sym: string) { return lastPrices[sym] }
function formatPrice(v: number | null) { 
  if (v === null) return '--'
  return v.toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 }) 
}
function formatPct(v: number) { return `${(v * 100).toFixed(2)}%` }
function fmtTime(ts: number) { return formatWithTz(ts, { hour: '2-digit', minute: '2-digit' }) }
function fmtTimeSeconds(ts: number) { return formatWithTz(ts, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
function badge(t: string) { return t === 'rapid_drop' ? '极速下跌' : '极速上涨' }
function anchorLabel(a: any) { return a.alert_type === 'rapid_rebound' ? '低点' : '高点' }
function anchorPrice(a: any) { return a.reference.anchor_price ?? a.reference.peak_price }
function anchorTs(a: any) { return a.reference.anchor_ts ?? a.reference.peak_ts }
function triggerPrice(a: any) { return a.reference.current_price ?? a.reference.close }
function triggerTs(a: any) { return a.reference.current_ts ?? a.ts }

// 修正逻辑：下跌显示为负值
function moveFromAnchor(a: any) { 
  const val = a.reference.move_from_anchor ?? (a.alert_type === 'rapid_drop' ? a.reference.drop_from_peak : a.reference.rise_from_trough);
  return a.alert_type === 'rapid_drop' ? -Math.abs(val) : Math.abs(val);
}

function formatThreshold(a: any) {
  const sign = a.alert_type === 'rapid_drop' ? '-' : ''
  return `${sign}${(a.magnitude * 100).toFixed(1)}%`
}

function pctOrDash(v: any) { return v === null ? '--' : formatPct(v) }

function setDayOpens(sym: string, map: any, legacy: any) {
  const fb = legacy ?? null
  tzOptions.forEach(o => { dayOpens[o.key][sym] = map?.[o.key] ?? fb })
}

function resolveWsUrl() {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search)
    const override = params.get('ws')
    if (override) return override
    const host = window.location.hostname
    if (host === 'localhost' || host === '127.0.0.1') return 'ws://127.0.0.1:9876'
  }
  return 'wss://ws.flowbyte.me'
}

function resolveAlertsUrl() {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search)
    const override = params.get('http')
    if (override) return override
    const host = window.location.hostname
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://127.0.0.1:9877/alerts/recent'
    }
  }
  const wsUrl = resolveWsUrl()
  if (wsUrl.startsWith('wss://')) return wsUrl.replace('wss://', 'https://') + '/alerts/recent'
  if (wsUrl.startsWith('ws://')) return wsUrl.replace('ws://', 'http://') + '/alerts/recent'
  return 'https://ws.flowbyte.me/alerts/recent'
}

function shouldFetchInitialAlerts() {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  if (params.get('http')) return true
  const host = window.location.hostname
  return host === 'localhost' || host === '127.0.0.1'
}

function connect() {
  ws = new WebSocket(resolveWsUrl())
  ws.onopen = () => {
    connectionState.value = 'open'
    playAlertSound()
  }
  ws.onmessage = (e) => handleMessage(JSON.parse(e.data))
  ws.onclose = () => { connectionState.value = 'closed'; setTimeout(connect, 3000) }
}

async function fetchInitialAlerts() {
  if (!shouldFetchInitialAlerts()) return
  try {
    const res = await fetch(resolveAlertsUrl())
    const data = await res.json()
    if (data.alerts) alerts.splice(0, alerts.length, ...data.alerts.map((a: any) => ({ ...a, id: `${a.symbol}-${a.ts}` })))
  } catch (e) {}
}

function initAlertAudio() {
  if (alertAudio) return
  alertAudio = new Audio(ALERT_AUDIO_URL)
  alertAudio.preload = 'auto'
  alertAudio.load()
}

function playAlertSound() {
  initAlertAudio()
  if (!alertAudio) return
  alertAudio.currentTime = 0
  alertAudio.play().catch(() => {
    // Autoplay may be blocked until user interaction.
  })
}

onBeforeUnmount(() => { ws?.close(); charts.forEach(c => c.dispose()) })
watch(selectedTz, () => {
  updateCharts()
})
</script>

<style scoped>
.alerts-page {
  --primary-bg: #f8fafc;
  --card-bg: #ffffff;
  --up-color: #16c784;
  --down-color: #ef4444;
  --text-main: #1e293b;
  --text-sub: #64748b;
  --border-color: #e2e8f0;
  --main-price-font: inherit;
  min-height: 100vh;
  background-color: var(--primary-bg);
  padding: 24px 16px;
  color: var(--text-main);
}
.container { max-width: 1400px; margin: 0 auto; }

/* Header */
.alerts-hero { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }
h1 { font-size: 32px; font-weight: 800; margin: 0; }
.brand-dot { color: var(--up-color); }
.hero-controls { display: flex; gap: 12px; }
.connection { display: flex; align-items: center; gap: 8px; padding: 8px 16px; background: #fff; border: 1px solid var(--border-color); border-radius: 12px; font-size: 14px; }
.connection .dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1; }
.connection.live .dot { background: var(--up-color); box-shadow: 0 0 8px var(--up-color); }
.fancy-select { border: 1px solid var(--border-color); padding: 8px; border-radius: 12px; outline: none; background: #fff; cursor: pointer; font-weight: 600; }

/* 价格卡片 */
.cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 24px; margin-bottom: 32px; }
.crypto-card { background: #fff; border: 1px solid var(--border-color); border-radius: 24px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
.card-content { padding: 24px; position: relative; }
.card-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.symbol-name { font-size: 20px; font-weight: 800; }
.pct-badge { padding: 4px 10px; border-radius: 8px; font-weight: 700; font-size: 14px; font-family: var(--main-price-font); font-variant-numeric: tabular-nums; }
.pct-badge.up { background: rgba(22, 199, 132, 0.1); color: var(--up-color); }
.pct-badge.down { background: rgba(239, 68, 68, 0.1); color: var(--down-color); }

.price-section { margin-bottom: 16px; position: relative; z-index: 2; }
.main-price { font-size: clamp(24px, 3vw, 34px); font-weight: 850; line-height: 1.2; margin: 4px 0; letter-spacing: -1px; font-family: var(--main-price-font); font-variant-numeric: tabular-nums; white-space: nowrap; }
.open-price { font-size: 13px; color: var(--text-sub); display: flex; align-items: center; gap: 6px; }
.open-price .val { font-weight: 700; color: var(--text-main); font-family: var(--main-price-font); font-variant-numeric: tabular-nums; }

.chart-container { height: 100px; margin: 0 -24px -24px -24px; position: relative; z-index: 1; }
.chart { width: 100%; height: 100%; }

/* 预警列表 */
.alerts-section { background: #fff; border: 1px solid var(--border-color); border-radius: 24px; padding: 24px; }
.section-header { display: flex; justify-content: space-between; margin-bottom: 20px; }
.alert-item { border: 1px solid var(--border-color); border-radius: 16px; margin-bottom: 20px; position: relative; padding: 20px; }
.alert-status-line { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; border-radius: 4px 0 0 4px; }
.alert-status-line.rapid_drop { background: var(--down-color); }
.alert-status-line.rapid_rebound { background: var(--up-color); }

.alert-top { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.alert-type-pill { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 800; }
.alert-type-pill.rapid_drop { background: #fef2f2; color: var(--down-color); }
.alert-type-pill.rapid_rebound { background: #f0fdf4; color: var(--up-color); }
.alert-symbol-info { font-weight: 700; display: flex; gap: 8px; }
.alert-symbol-info .mag,
.alert-symbol-info .win { font-family: var(--main-price-font); font-variant-numeric: tabular-nums; }

.alert-flow { 
  display: flex; align-items: center; gap: 12px; 
  background: #f8fafc; padding: 12px 16px; border-radius: 12px; margin-bottom: 16px;
  border: 1px solid #f1f5f9;
}
.flow-info-block { display: flex; flex-direction: column; min-width: 90px; }
.b-label { font-size: 11px; color: var(--text-sub); text-transform: uppercase; margin-bottom: 2px; }
.b-label.highlight { color: #3b82f6; font-weight: 800; }
.b-date, .b-time { font-size: 13px; font-family: var(--main-price-font); font-weight: 600; line-height: 1.2; white-space: nowrap; font-variant-numeric: tabular-nums; }

/* 回退并优化的指示器样式 (Box Style) */
.flow-price-indicator { 
  font-size: clamp(14px, 2vw, 18px); font-weight: 800; font-family: var(--main-price-font); font-variant-numeric: tabular-nums;
  background: #fff; padding: 6px 10px; border-radius: 8px; border: 1px solid #e2e8f0; flex: 1 1 0; text-align: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
  min-width: 0; white-space: nowrap;
}
.flow-price-indicator.trigger { color: #3b82f6; border-color: #bfdbfe; background: #eff6ff; }
.flow-arrow { color: #cbd5e1; font-size: 18px; font-weight: bold; }

/* 页脚 Fancy 重构：两行展示 */
.alert-footer-fancy {
  border-top: 1px dashed var(--border-color);
  padding-top: 16px;
}
.footer-stats { display: flex; flex-direction: column; gap: 8px; }
.stat-row { display: flex; justify-content: space-between; align-items: center; max-width: 280px; }
.stat-label { font-size: 12px; color: var(--text-sub); font-weight: 500; }
.stat-value { font-size: 14px; font-weight: 800; font-family: var(--main-price-font); font-variant-numeric: tabular-nums; }
.stat-value.secondary { color: var(--text-main); opacity: 0.6; }

.text-red { color: var(--down-color); }
.text-green { color: var(--up-color); }

@media (max-width: 768px) {
  .alert-flow { flex-wrap: wrap; gap: 12px; }
  .flow-arrow { transform: rotate(90deg); margin: 0 auto; }
}
</style>
