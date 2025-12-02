#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

function usage() {
  console.error('Usage: node convert-stations.mjs <input.csv> <out.js>')
  process.exit(1)
}

const [, , input, out] = process.argv
if (!input || !out) usage()

function parseCSV(text) {
  const rows = []
  let i = 0
  const n = text.length
  let row = []
  let field = ''
  let inQuotes = false
  for (; i < n; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { // escaped quote
          field += '"'; i++
        } else {
          inQuotes = false
        }
      } else {
        field += c
      }
    } else {
      if (c === '"') {
        inQuotes = true
      } else if (c === ',') {
        row.push(field)
        field = ''
      } else if (c === '\n') {
        row.push(field)
        rows.push(row)
        row = []
        field = ''
      } else if (c === '\r') {
        // ignore, handle on \n
      } else {
        field += c
      }
    }
  }
  // flush last field
  row.push(field)
  rows.push(row)
  return rows
}

function pick(obj, candidates) {
  for (const name of candidates) {
    if (Object.prototype.hasOwnProperty.call(obj, name)) {
      const v = obj[name]
      if (v !== undefined && String(v).trim() !== '') return v
    }
  }
  return null
}

const csvText = fs.readFileSync(path.resolve(input), 'utf8')
const rows = parseCSV(csvText).filter(r => r.length && r.some(x => String(x).trim() !== ''))
if (rows.length === 0) {
  console.error('Empty CSV or failed to parse:', input)
  process.exit(2)
}

const headers = rows[0].map(h => String(h).trim())
const dataRows = rows.slice(1)

const objects = dataRows.map((r) => {
  const obj = {}
  headers.forEach((h, idx) => { obj[h] = r[idx] ?? '' })
  const name = pick(obj, ['路徑名稱','路線名稱','路線','路名'])
  const direction = pick(obj, ['路程','方向','去回程'])
  const seq = pick(obj, ['站次','站序','序號','順序'])
  const stopName = pick(obj, ['站點','站名','站點名稱'])
  const eta = pick(obj, ['首站到此站時間','預估到站(分)','行駛時間(分)','行車時間','預估行車(分)'])
  const lat = pick(obj, ['去程緯度','緯度','Lat','lat','Latitude','Y','y'])
  const lng = pick(obj, ['去程經度','經度','Lng','lng','Longitude','X','x'])

  const toInt = (x) => x == null || String(x).trim() === '' ? null : (Number.isFinite(Number(x)) ? Number(x) : String(x))
  const toNum = (x) => x == null || String(x).trim() === '' ? null : (Number.isFinite(Number(x)) ? Number(x) : String(x))

  return {
    '路徑名稱': name ?? null,
    '路程': direction ?? null,
    '站次': toInt(seq),
    '站點': stopName ?? null,
    '首站到此站時間': toInt(eta),
    '去程緯度': toNum(lat),
    '去程經度': toNum(lng),
  }
})

const cleaned = objects.filter(o => o['路徑名稱'] || o['站點'] || o['去程緯度'] || o['去程經度'])
const outJs = 'export default ' + JSON.stringify(cleaned) + '\n'
fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true })
fs.writeFileSync(path.resolve(out), outJs, 'utf8')
console.log(`已輸出 ${cleaned.length} 筆 -> ${out}`)

