// Generated: 2026-07-17
// Personality Signature — 데이터 아트 프로토타입
// 설문(22문항, 1~5점) → 성향벡터(6종) + MBTI(4축) → 문양(폴리라인) 생성 → SVG/로봇JSON 내보내기
// 문양은 "획(폴리라인)" 단위로 생성 → 화면·SVG·로봇 펜플로터가 같은 데이터를 공유한다.

import React, { useState, useEffect, useMemo, useRef } from "react";

/* ────────────────────────────────────────────────────────────
   1. 설문 정의
   각 문항은 1~5점. axis: 어느 MBTI 축에 속하는지("EI"|"NS"|"TF"|"JP"|null).
   dir: 그 축의 "앞글자(E/N/T/J)" 방향으로 그대로 더하면 1, 반대(역채점) 문항이면 -1.
   실제 MBTI 계열 검사처럼 각 축을 5문항(역채점 포함)의 평균으로 계산해 정확도를 높인다.
   axis:null 문항은 MBTI 판정에는 관여하지 않고 문양 조형 벡터 전용으로만 쓰인다.
──────────────────────────────────────────────────────────── */
const QUESTIONS = [
  // ── E / I ──
  { id: 1, text: "새로운 사람을 만나면 내가 먼저 말을 걸고 대화를 이끄는 편이다", tag: "활력", axis: "EI", dir: 1 },
  { id: 2, text: "사람들과 오래 어울리고 나면 오히려 에너지가 차오르는 것을 느낀다", tag: "교류", axis: "EI", dir: 1 },
  { id: 3, text: "사람들과 오래 있고 나면 혼자만의 시간이 꼭 필요하다", tag: "고독", axis: "EI", dir: -1 },
  { id: 4, text: "모임에서 이야기의 중심에 서는 것이 어색하지 않다", tag: "주도", axis: "EI", dir: 1 },
  { id: 5, text: "말을 꺼내기 전에 머릿속에서 생각을 충분히 정리하는 편이다", tag: "숙고", axis: "EI", dir: -1 },
  // ── N / S ──
  { id: 6, text: "구체적인 사실보다 전체적인 흐름과 가능성에 먼저 눈이 간다", tag: "직관", axis: "NS", dir: 1 },
  { id: 7, text: "지금 눈앞의 현실보다 앞으로 어떻게 될지 상상하는 것을 즐긴다", tag: "상상", axis: "NS", dir: 1 },
  { id: 8, text: "익숙한 방식보다 새로운 방식을 시도해보고 싶다", tag: "발상", axis: "NS", dir: 1 },
  { id: 9, text: "눈에 보이고 손에 잡히는 구체적인 정보를 더 신뢰한다", tag: "현실감각", axis: "NS", dir: -1 },
  { id: 10, text: "이미 검증된 방법을 그대로 따르는 것이 더 효율적이라고 생각한다", tag: "실용", axis: "NS", dir: -1 },
  // ── T / F ──
  { id: 11, text: "결정을 내릴 때 감정보다 논리와 근거를 먼저 따진다", tag: "논리", axis: "TF", dir: 1 },
  { id: 12, text: "누군가 고민을 말하면 위로보다 해결책부터 제시하고 싶어진다", tag: "해결", axis: "TF", dir: 1 },
  { id: 13, text: "옳고 그름을 판단할 때 원칙과 기준이 감정보다 우선한다", tag: "원칙", axis: "TF", dir: 1 },
  { id: 14, text: "상대방의 기분이 상하지 않을지가 판단의 큰 기준이 된다", tag: "공감", axis: "TF", dir: -1 },
  { id: 15, text: "예술 작품이나 음악에 쉽게 마음이 움직인다", tag: "감성", axis: "TF", dir: -1 },
  // ── J / P ──
  { id: 16, text: "여행을 가기 전에 일정을 세세하게 짜 두는 편이다", tag: "계획", axis: "JP", dir: 1 },
  { id: 17, text: "마감 기한보다 미리 일을 끝내 놓아야 마음이 편하다", tag: "여유", axis: "JP", dir: 1 },
  { id: 18, text: "정해진 규칙과 절차를 따르는 것이 마음 편하다", tag: "규칙", axis: "JP", dir: 1 },
  { id: 19, text: "계획이 바뀌어도 그때그때 즉흥적으로 대응하는 것을 즐긴다", tag: "즉흥", axis: "JP", dir: -1 },
  { id: 20, text: "마감 직전에 몰아서 할 때 오히려 집중이 잘 된다", tag: "막판", axis: "JP", dir: -1 },
  // ── 문양 전용 (MBTI 축에는 관여하지 않음) ──
  { id: 21, text: "실패할 위험이 있어도 익숙한 것보다 새로운 도전을 택하는 편이다", tag: "도전", axis: null, dir: 1 },
  { id: 22, text: "한 번 시작한 일은 다른 데 한눈팔지 않고 끝까지 파고드는 편이다", tag: "몰입", axis: null, dir: 1 },
];

const SCALE = ["전혀\n아니다", "아니다", "보통", "그렇다", "매우\n그렇다"];

/* ────────────────────────────────────────────────────────────
   2. 응답 → 지표 계산
   answers: [a1..a22], 각 1~5.  n = (a-1)/4  (0~1 정규화)
──────────────────────────────────────────────────────────── */
function analyze(answers) {
  const n = answers.map((a) => (a - 1) / 4); // 0~1
  const nz = (id) => n[id - 1]; // 1-based 문항 번호로 접근
  const inv = (x) => 1 - x;
  const mean = (...xs) => xs.reduce((s, v) => s + v, 0) / xs.length;

  // MBTI 4축 (0~100, 값이 높을수록 앞글자 E / N / T / J 쪽)
  // 각 축 = 그 축에 속한 5개 문항(역채점 포함)의 평균. 문항 하나하나가 아니라 여러 신호의
  // 평균으로 판정하므로, 응답자가 비슷한 점수를 준 문항 한두 개 때문에 축 전체가 50으로
  // 고정되던 문제(예: 항상 ENTJ만 나오던 현상)가 사라지고 실제 검사처럼 오차가 상쇄된다.
  const axisVals = { EI: [], NS: [], TF: [], JP: [] };
  QUESTIONS.forEach((q, i) => {
    if (!q.axis) return;
    axisVals[q.axis].push(q.dir === 1 ? n[i] : inv(n[i]));
  });
  const axes = {
    EI: 100 * mean(...axisVals.EI),
    NS: 100 * mean(...axisVals.NS),
    TF: 100 * mean(...axisVals.TF),
    JP: 100 * mean(...axisVals.JP),
  };
  const type =
    (axes.EI >= 50 ? "E" : "I") +
    (axes.NS >= 50 ? "N" : "S") +
    (axes.TF >= 50 ? "T" : "F") +
    (axes.JP >= 50 ? "J" : "P");

  // 성향 벡터 6종 (0~100) — 문양 조형 파라미터로 쓰인다
  const vector = {
    creativity: 100 * mean(nz(6), nz(7), nz(8)),       // 직관·상상·발상
    planning: 100 * mean(nz(16), nz(17), nz(18)),      // 계획·여유·규칙(J 방향)
    sociability: 100 * mean(nz(1), nz(2), inv(nz(3))), // 활력·교류·고독역
    challenge: 100 * mean(nz(8), nz(21)),               // 발상 + 도전 전용 문항
    focus: 100 * nz(22),                                // 몰입 전용 문항
    sensitivity: 100 * nz(15),                          // 감성(F 문항)
  };

  // 재현 가능한 시드(같은 응답 → 같은 문양). 방문자별 고유가 필요하면 Date.now() 섞으면 됨.
  const seed = hashInts(answers.concat(answers.map((a, i) => a * (i + 3))));
  return { axes, type, vector, seed };
}

/* ────────────────────────────────────────────────────────────
   3. 유틸 (해시 · 시드 난수 · 좌표)
──────────────────────────────────────────────────────────── */
function hashInts(arr) {
  let h = 2166136261;
  for (const v of arr) { h ^= v; h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const map = (v, a, b, c, d) => c + ((v - a) / (b - a)) * (d - c);
const polar = (cx, cy, ang, r) => [cx + Math.cos(ang) * r, cy + Math.sin(ang) * r];
function quad(p0, pc, p1, seg = 14) { // 2차 베지어 → 폴리라인
  const pts = [];
  for (let i = 0; i <= seg; i++) {
    const t = i / seg, u = 1 - t;
    pts.push([u*u*p0[0]+2*u*t*pc[0]+t*t*p1[0], u*u*p0[1]+2*u*t*pc[1]+t*t*p1[1]]);
  }
  return pts;
}
function circlePts(cx, cy, r, n = 44) {
  const p = [];
  for (let i = 0; i <= n; i++) { const a = (i / n) * 2 * Math.PI; p.push(polar(cx, cy, a, r)); }
  return p;
}


/* ────────────────────────────────────────────────────────────
   4. MBTI 16종 → 문양 레시피
   각 유형은 두 부분으로 구성된다.
     silhouette : 문양 전체의 "외곽 형태"(하트·방패·꽃·별·잎·육각 등).
                  → 이 형태를 극좌표로 샘플해 중첩 윤곽·물결 기요셰를 그 위에 얹으므로
                    유형마다 실제로 다른 실루엣이 나온다(하트는 하트, 방패는 방패).
     recipe     : 중앙 메달리온에 쌓을 "내부 장식링" 목록(원형 장식).
   silhouette 종류: heart · shield · leaf · hexagon · diamond · gear · wave
                   · blossom(꽃) · bud(홑꽃) · crystal(결정별) · star12(잔별) · circle
   내부링 종류: harm · spiro · petal · star · scallop · bead · spoke · rose · circle
──────────────────────────────────────────────────────────── */
const FAMILY = {
  // NT — 결정/별 (예리·기하)
  INTJ: { label: "결정 성좌", silhouette: "crystal", recipe: ["star", "spiro", "bead"] },
  INTP: { label: "격자 결정", silhouette: "hexagon", recipe: ["star", "spoke", "bead"] },
  ENTJ: { label: "성휘(별빛)", silhouette: "star12", recipe: ["spiro", "star", "bead"] },
  ENTP: { label: "분기 결정", silhouette: "crystal", recipe: ["spiro", "rose", "scallop"] },
  // NF — 꽃/만다라 (유기·곡선)
  INFJ: { label: "나선 꽃", silhouette: "blossom", recipe: ["spiro", "petal", "scallop"] },
  INFP: { label: "홑꽃", silhouette: "bud", recipe: ["petal", "rose", "bead"] },
  ENFJ: { label: "겹꽃 만다라", silhouette: "blossom", recipe: ["petal", "scallop", "rose"] },
  ENFP: { label: "유기 만다라", silhouette: "blossom", recipe: ["rose", "petal", "spiro"] },
  // ST — 기하/구조 (건축적)
  ISTJ: { label: "육각 격자", silhouette: "hexagon", recipe: ["star", "spoke", "bead"] },
  ISTP: { label: "톱니 세공", silhouette: "gear", recipe: ["star", "spoke", "scallop"] },
  ESTJ: { label: "각진 방패", silhouette: "shield", recipe: ["star", "spoke", "bead"] },
  ESTP: { label: "화살 방사", silhouette: "diamond", recipe: ["spoke", "star", "bead"] },
  // SF — 물결/잎 (부드러움)
  ISFJ: { label: "물결 고리", silhouette: "wave", recipe: ["scallop", "rose", "bead"] },
  ISFP: { label: "잎사귀", silhouette: "leaf", recipe: ["rose", "petal", "bead"] },
  ESFJ: { label: "하트 로제트", silhouette: "heart", recipe: ["petal", "rose", "bead"] },
  ESFP: { label: "파동 별", silhouette: "wave", recipe: ["spiro", "scallop", "bead"] },
};

/* ────────────────────────────────────────────────────────────
   5. 밴드 빌더 (모두 N겹 대칭 폴리라인 배열 반환)
──────────────────────────────────────────────────────────── */
function gcd(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { const t = a % b; a = b; b = t; } return a || 1; }

// 기요셰/로즈 하모닉 링: r(θ)=R + A·cos(Nθ+off) + A2·cos(2Nθ)  → 닫힌 물결 곡선
function bHarm(cx, cy, R, N, sharp, curv, off, ornate = 0) {
  const amp = R * (0.05 + 0.11 * curv);
  const amp2 = amp * (0.35 + 0.55 * sharp);
  const amp3 = amp * 0.45 * ornate;                     // 복잡도 → 3차 하모닉(레이스 실루엣)
  const n = Math.max(320, N * 46), p = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI;
    const r = R + amp * Math.cos(N * a + off) + amp2 * Math.cos(2 * N * a) + amp3 * Math.cos(3 * N * a - off);
    p.push(polar(cx, cy, a, r));
  }
  return [p];
}

// 스피로그래프(하이포트로코이드): N개 로브. x=(Rg-rg)cos t + d·cos((Rg-rg)/rg·t)
function bSpiro(cx, cy, R, N, sharp, curv, off, ornate = 0) {
  const Rg = N;
  let rg = 1; for (let k = N - 1; k >= 2; k--) if (gcd(N, k) === 1) { rg = k; break; } // N과 서로소인 최대 내륜
  const d = rg * (0.5 + 0.45 * sharp) * (1 + ornate * 0.9);  // 복잡도↑ → 프롤레이트(내부 루프 생성)
  const revs = rg;                        // rg바퀴 후 정확히 닫힘
  const n = Math.max(900, N * 130), raw = [];
  let maxr = 0;
  for (let i = 0; i <= n; i++) {
    const t = (i / n) * 2 * Math.PI * revs + off;
    const x = (Rg - rg) * Math.cos(t) + d * Math.cos(((Rg - rg) / rg) * t);
    const y = (Rg - rg) * Math.sin(t) - d * Math.sin(((Rg - rg) / rg) * t);
    raw.push([x, y]); maxr = Math.max(maxr, Math.hypot(x, y));
  }
  const s = R / (maxr || 1);
  return [raw.map(([x, y]) => [cx + x * s, cy + y * s])];
}

// 겹꽃잎 링: N개 꽃잎(바깥+안쪽 이중 윤곽)
function petalOutline(cx, cy, ang, rIn, rOut, curv, sharp) {
  const w = (rOut - rIn) * (0.40 - 0.24 * sharp);
  const px = Math.cos(ang + Math.PI / 2), py = Math.sin(ang + Math.PI / 2);
  const p0 = polar(cx, cy, ang, rIn), tip = polar(cx, cy, ang, rOut);
  const midR = rIn + (rOut - rIn) * (0.52 + 0.1 * curv), bow = w * (0.6 + curv);
  const mL = [cx + Math.cos(ang) * midR + px * bow, cy + Math.sin(ang) * midR + py * bow];
  const mR = [cx + Math.cos(ang) * midR - px * bow, cy + Math.sin(ang) * midR - py * bow];
  return quad(p0, mL, tip, 16).concat(quad(tip, mR, p0, 16).slice(1));
}
function bPetal(cx, cy, rIn, rOut, N, sharp, curv) {
  const out = [];
  for (let k = 0; k < N; k++) {
    const ang = (k * 2 * Math.PI) / N - Math.PI / 2;
    out.push(petalOutline(cx, cy, ang, rIn, rOut, curv, sharp));
    out.push(petalOutline(cx, cy, ang, rIn, rIn + (rOut - rIn) * 0.62, curv, sharp)); // 안쪽 겹
  }
  return out;
}

// 별 다각형 {N/m}: N꼭짓점을 m칸씩 연결(이슬람 기하). gcd만큼 분할 스트로크.
function bStar(cx, cy, R, N, sharp) {
  const m = Math.max(2, Math.min(Math.floor(N / 2), 2 + Math.round(sharp * (N / 2 - 2)))); // 뾰족함↑ → step↑
  const v = [];
  for (let k = 0; k < N; k++) v.push(polar(cx, cy, (k * 2 * Math.PI) / N - Math.PI / 2, R));
  const g = gcd(N, m), out = [];
  for (let s = 0; s < g; s++) {
    const path = []; let idx = s;
    do { path.push(v[idx]); idx = (idx + m) % N; } while (idx !== s);
    path.push(v[s]); out.push(path);
  }
  return out;
}

// 레이스 화환: 인접 살 사이 N개의 원호(안/밖으로 불룩)
function bScallop(cx, cy, R, N, depth, outward) {
  const out = [], sign = outward ? 1 : -1;
  for (let k = 0; k < N; k++) {
    const a0 = (k * 2 * Math.PI) / N - Math.PI / 2, a1 = ((k + 1) * 2 * Math.PI) / N - Math.PI / 2;
    const p0 = polar(cx, cy, a0, R), p1 = polar(cx, cy, a1, R);
    const mid = (a0 + a1) / 2, ctrl = polar(cx, cy, mid, R + sign * depth);
    out.push(quad(p0, ctrl, p1, 12));
  }
  return out;
}

// 구슬 링: N개 작은 원
function bBead(cx, cy, R, N, beadR) {
  const out = [];
  for (let k = 0; k < N; k++) {
    const a = (k * 2 * Math.PI) / N - Math.PI / 2, c = polar(cx, cy, a, R);
    out.push(circlePts(c[0], c[1], beadR, 16));
  }
  return out;
}

// 방사살: N개 반경선
function bSpoke(cx, cy, rIn, rOut, N) {
  const out = [];
  for (let k = 0; k < N; k++) {
    const a = (k * 2 * Math.PI) / N - Math.PI / 2;
    out.push([polar(cx, cy, a, rIn), polar(cx, cy, a, rOut)]);
  }
  return out;
}

function buildBand(name, cx, cy, R, outerR, N, sharp, curv, off, rng, ornate = 0) {
  const inner = R * 0.6;
  switch (name) {
    case "harm": return bHarm(cx, cy, R, N, sharp, curv, off, ornate);
    case "spiro": return bSpiro(cx, cy, R, N, sharp, curv, off, ornate);
    case "petal": return bPetal(cx, cy, inner, R, N, sharp, curv);
    case "star": return bStar(cx, cy, R, N, sharp);
    case "scallop": return bScallop(cx, cy, R, N, R * (0.06 + 0.05 * curv), rng() > 0.5);
    case "bead": return bBead(cx, cy, R, N, R * 0.05);
    case "spoke": return bSpoke(cx, cy, inner, R, N);
    case "rose": return bRose(cx, cy, R, Math.max(3, Math.round(N / 2)), off);
    case "circle": return [circlePts(cx, cy, R, 140)];
    default: return bHarm(cx, cy, R, N, sharp, curv, off);
  }
}

/* 로즈 곡선(rhodonea) r=R·cos(kθ): k 홀수→k장, 짝수→2k장 꽃잎. 내부 장식용. */
function bRose(cx, cy, R, k, off = 0) {
  const n = Math.max(400, k * 90), p = [];
  for (let i = 0; i <= n; i++) {
    const phi = (i / n) * 2 * Math.PI;
    const r = R * Math.cos(k * phi + off);          // r<0이면 반대편에 찍혀 고전적 장미 형태
    p.push([cx + Math.cos(phi) * r, cy + Math.sin(phi) * r]);
  }
  return [p];
}

/* ────────────────────────────────────────────────────────────
   5-b. 실루엣 형태 엔진
   - 각 형태를 "원점 기준 점 구름(raw)"으로 생성한 뒤 normalizeShape로
     무게중심 정렬 + 반경 R 정규화 → {pts, polar} 반환.
   - polar = [[θ,ρ], …] (중심 기준). 이 극좌표를 재활용해
       shapeRing  : 형태를 s배 축소한 닫힌 윤곽
       shapeRipple: 형태 반경에 cos 물결을 얹은 기요셰 링
     을 만들어, 모든 장식이 유형 고유의 외곽 형태를 따라간다.
──────────────────────────────────────────────────────────── */
// Gielis 슈퍼포뮬러: r(φ)=(|cos(mφ/4)/a|^n2 + |sin(mφ/4)/b|^n3)^(-1/n1)
// m=대칭 수, n1↓→뾰족(별), n1=n2=n3 큼→다각형, =1 근처→부드러운 꽃.
function superRaw({ m, n1, n2, n3, a = 1, b = 1 }, steps = 1440) {
  const raw = [];
  for (let i = 0; i <= steps; i++) {
    const phi = (i / steps) * 2 * Math.PI;
    const t1 = Math.pow(Math.abs(Math.cos((m * phi) / 4) / a), n2);
    const t2 = Math.pow(Math.abs(Math.sin((m * phi) / 4) / b), n3);
    let r = Math.pow(t1 + t2, -1 / n1);
    if (!isFinite(r)) r = 0;
    raw.push([Math.cos(phi) * r, Math.sin(phi) * r]);
  }
  return raw;
}
function rotateRaw(raw, ang) {
  const c = Math.cos(ang), s = Math.sin(ang);
  return raw.map(([x, y]) => [x * c - y * s, x * s + y * c]);
}
// 정다각형(직선 변). rot으로 꼭짓점 방향, stretchY로 세로 비율.
function polygonRaw(sides, { rot = -Math.PI / 2, stretchY = 1, per = 26 } = {}) {
  const v = [];
  for (let k = 0; k < sides; k++) {
    const a = rot + (k * 2 * Math.PI) / sides;
    v.push([Math.cos(a), Math.sin(a) * stretchY]);
  }
  const raw = [];
  for (let k = 0; k < sides; k++) {
    const p0 = v[k], p1 = v[(k + 1) % sides];
    for (let i = 0; i < per; i++) { const t = i / per; raw.push([p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t]); }
  }
  raw.push(v[0]);
  return raw;
}
// 톱니바퀴: tanh로 매끈한 사각파 → 이(teeth)개의 톱니.
function gearRaw(teeth, depth = 0.17) {
  const base = 1 - depth, n = teeth * 60, raw = [];
  for (let i = 0; i <= n; i++) {
    const phi = (i / n) * 2 * Math.PI;
    const tooth = 0.5 + 0.5 * Math.tanh(4 * Math.cos(teeth * phi));
    const r = base + depth * tooth;
    raw.push([Math.cos(phi) * r, Math.sin(phi) * r]);
  }
  return raw;
}
// 물결 원: lobes개의 완만한 부채꼴.
function waveRaw(lobes, amp = 0.12) {
  const n = lobes * 44, raw = [];
  for (let i = 0; i <= n; i++) { const phi = (i / n) * 2 * Math.PI; const r = 1 + amp * Math.cos(lobes * phi); raw.push([Math.cos(phi) * r, Math.sin(phi) * r]); }
  return raw;
}
// 하트(고전 매개변수 곡선). y는 화면 좌표(아래 +)라 뒤집는다.
function heartRaw() {
  const n = 520, raw = [];
  for (let i = 0; i <= n; i++) {
    const t = (i / n) * 2 * Math.PI;
    const x = 16 * Math.pow(Math.sin(t), 3);
    const y = 13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t);
    raw.push([x, -y]);
  }
  return raw;
}
// 헤럴드릭 방패: 아치형 윗변 → 곧은 어깨 → 곡선 옆면이 아래 한 점으로.
function shieldRaw() {
  const w = 1, topY = -1.15, shoulderY = -0.45, botY = 1.5, raw = [];
  const arch = (x) => topY - 0.12 * (1 - (x / w) * (x / w));
  const segTop = 44;
  for (let i = 0; i <= segTop; i++) { const x = -w + 2 * w * (i / segTop); raw.push([x, arch(x)]); }
  const segS = 10;
  for (let i = 1; i <= segS; i++) raw.push([w, topY + (shoulderY - topY) * (i / segS)]);
  const qR = quad([w, shoulderY], [w * 1.02, botY * 0.55], [0, botY], 30);
  for (let i = 1; i < qR.length; i++) raw.push(qR[i]);
  const qL = quad([0, botY], [-w * 1.02, botY * 0.55], [-w, shoulderY], 30);
  for (let i = 1; i < qL.length; i++) raw.push(qL[i]);
  for (let i = 1; i <= segS; i++) raw.push([-w, shoulderY + (topY - shoulderY) * (i / segS)]);
  return raw;
}
// 형태 이름 → 정규화된 {pts, polar}. N(대칭 수)로 꽃잎/톱니 수도 함께 변한다.
function makeShape(name, cx, cy, R, N) {
  const ci = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v)));
  let raw;
  switch (name) {
    case "heart":   raw = heartRaw(); break;
    case "shield":  raw = shieldRaw(); break;
    case "leaf":    raw = rotateRaw(superRaw({ m: 2, n1: 0.6, n2: 0.6, n3: 0.6 }), Math.PI / 2); break;
    case "hexagon": raw = polygonRaw(6, { rot: -Math.PI / 2 }); break;
    case "diamond": raw = polygonRaw(4, { rot: -Math.PI / 2, stretchY: 1.28 }); break;
    case "gear":    raw = gearRaw(ci(N, 10, 16)); break;
    case "wave":    raw = waveRaw(ci(N, 8, 14), 0.12); break;
    case "blossom": raw = superRaw({ m: ci(N / 2, 4, 8), n1: 1, n2: 1.7, n3: 1.7 }); break;
    case "bud":     raw = superRaw({ m: 5, n1: 1, n2: 1.8, n3: 1.8 }); break;
    case "crystal": raw = superRaw({ m: ci(N / 2, 5, 8), n1: 0.35, n2: 0.4, n3: 0.4 }); break;
    case "star12":  raw = superRaw({ m: ci(N, 10, 16), n1: 0.5, n2: 0.6, n3: 0.6 }); break;
    default:        raw = superRaw({ m: 0, n1: 1, n2: 1, n3: 1 }); break; // circle
  }
  return normalizeShape(raw, cx, cy, R);
}
function normalizeShape(raw, cx, cy, R) {
  let gx = 0, gy = 0;
  for (const [x, y] of raw) { gx += x; gy += y; }
  gx /= raw.length; gy /= raw.length;
  let maxr = 0;
  for (const [x, y] of raw) { const d = Math.hypot(x - gx, y - gy); if (d > maxr) maxr = d; }
  const s = R / (maxr || 1), pts = [], polar = [];
  for (const [x, y] of raw) {
    const dx = (x - gx) * s, dy = (y - gy) * s;
    pts.push([cx + dx, cy + dy]);
    polar.push([Math.atan2(dy, dx), Math.hypot(dx, dy)]);
  }
  return { pts, polar };
}
// 형태를 s배 축소한 닫힌 윤곽
function shapeRing(shape, cx, cy, s) {
  return shape.polar.map(([th, rho]) => [cx + Math.cos(th) * rho * s, cy + Math.sin(th) * rho * s]);
}
// 형태 반경에 N겹 cos 물결을 얹은 기요셰 링(형태를 따라감)
function shapeRipple(shape, cx, cy, s, N, amp, off) {
  return shape.polar.map(([th, rho]) => {
    const rr = rho * s * (1 + amp * Math.cos(N * th + off));
    return [cx + Math.cos(th) * rr, cy + Math.sin(th) * rr];
  });
}

/* ────────────────────────────────────────────────────────────
   6. 문양 생성기 (지표 → 대칭 만다라 폴리라인)
──────────────────────────────────────────────────────────── */
function generateGlyph(type, V, seed, complexity = 0.7) {
  const rng = mulberry32(seed);
  const cx = 300, cy = 300;
  const spec = FAMILY[type] || FAMILY.INFP;

  const N = Math.round(map(V.creativity, 0, 100, 6, 14));      // 창의성 → 대칭 차수(꽃잎/별/톱니 수)
  const outerR = map(V.sociability, 0, 100, 205, 275);         // 사교성 → 외곽 크기
  const sharp = map(V.challenge, 0, 100, 0, 1);                // 도전성 → 뾰족함
  const curv = map(V.sensitivity, 0, 100, 0, 1);              // 감수성 → 곡선/물결 진폭
  const clean = map(V.planning, 0, 100, 0, 1);                // 계획성 → 정갈함
  const off = (1 - clean) * (Math.PI / N) * 0.9;             // 낮으면 스월(회전대칭은 유지)
  const ornate = complexity;                                  // 하모닉/루프 화려함

  // 유형 고유의 외곽 실루엣(하트·방패·꽃·별·잎…)을 극좌표로 준비
  const shape = makeShape(spec.silhouette, cx, cy, outerR, N);

  let strokes = [];

  // A) 매크로 실루엣: 형태를 축소 중첩한 윤곽선(문양 전체가 이 형태가 된다)
  const rings = 2 + (complexity > 0.55 ? 1 : 0);
  for (let i = 0; i < rings; i++) strokes.push(shapeRing(shape, cx, cy, 1 - i * 0.10));

  // B) 형태를 따라가는 물결 기요셰 링(외곽~내부 사이를 채운다)
  const ripN = Math.round(map(V.focus, 0, 100, 2, 4)) + (complexity > 0.6 ? 1 : 0);
  const amp = 0.03 + 0.05 * curv;
  for (let i = 0; i < ripN; i++) {
    const s = 0.84 - i * (0.30 / Math.max(1, ripN));
    strokes.push(shapeRipple(shape, cx, cy, s, N, amp * (1 - i * 0.15), off + (i * Math.PI) / N));
  }

  // C) 중앙 메달리온: recipe의 원형 장식링을 안쪽에 동심 배치
  const recipe = spec.recipe;
  const innerTop = outerR * 0.5;
  for (let b = 0; b < recipe.length; b++) {
    const t = recipe.length > 1 ? b / (recipe.length - 1) : 0;
    const R = innerTop * (1 - 0.72 * t);
    strokes = strokes.concat(buildBand(recipe[b], cx, cy, R, innerTop, N, sharp, curv, off, rng, ornate));
  }

  // D) 중앙 인장(작은 로제트 + 점)
  strokes = strokes.concat(bHarm(cx, cy, outerR * 0.08, N, sharp, curv, off, ornate));
  strokes.push(circlePts(cx, cy, outerR * 0.03, 20));
  return strokes;
}

/* ────────────────────────────────────────────────────────────
   7. 내보내기 (SVG · 로봇용 JSON)
──────────────────────────────────────────────────────────── */
function strokeLen(pts) {
  let d = 0;
  for (let i = 1; i < pts.length; i++) d += Math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]);
  return d;
}
function toPathD(pts) {
  return pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
}
function toSVG(strokes, meta) {
  const paths = strokes.map((s) => `  <path d="${toPathD(s)}" />`).join("\n");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600">
  <!-- ${meta.type} · Personality Signature -->
  <g fill="none" stroke="#1a1a1a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
${paths}
  </g>
</svg>`;
}
function toRobotJSON(strokes, meta) {
  // 로봇 펜플로터용: 각 stroke = 펜다운 1회. 좌표는 캔버스 px(600 기준). 실장비 스케일은 로봇측에서 변환.
  return JSON.stringify(
    { canvas: { w: 600, h: 600 }, units: "px", meta,
      strokes: strokes.map((s) => s.map((p) => [Math.round(p[0]*10)/10, Math.round(p[1]*10)/10])) },
    null, 0
  );
}
function download(name, text, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

/* ════════════════════════════════════════════════════════════
   UI
════════════════════════════════════════════════════════════ */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
.ps-root{--bg:#0d1017;--panel:#141a22;--ink:#ece4d3;--muted:#8b93a3;--brass:#c9a24b;--line:rgba(236,228,211,.12);
  min-height:100%;background:radial-gradient(120% 80% at 50% -10%,#151d29 0%,var(--bg) 60%);
  color:var(--ink);font-family:'Noto Sans KR',sans-serif;-webkit-font-smoothing:antialiased;}
.ps-wrap{max-width:820px;margin:0 auto;padding:40px 22px 64px;}
.ps-eyebrow{font-size:11px;letter-spacing:.42em;text-transform:uppercase;color:var(--brass);font-weight:500;}
.ps-title{font-family:'Gowun Batang',serif;font-weight:700;line-height:1.15;letter-spacing:-.01em;}
.ps-serif{font-family:'Gowun Batang',serif;}
.ps-muted{color:var(--muted);}
.ps-mono{font-family:'DM Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;}
.ps-btn{border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:12px 22px;border-radius:2px;
  font-size:14px;cursor:pointer;transition:.18s;font-family:inherit;letter-spacing:.02em;}
.ps-btn:hover{border-color:var(--brass);color:#fff;}
.ps-btn:focus-visible{outline:2px solid var(--brass);outline-offset:2px;}
.ps-primary{background:var(--brass);color:#1a1206;border-color:var(--brass);font-weight:500;}
.ps-primary:hover{background:#d8b25c;color:#1a1206;}
.ps-opt{display:flex;flex-direction:column;align-items:center;gap:8px;flex:1;min-width:0;
  border:1px solid var(--line);background:rgba(255,255,255,.015);border-radius:3px;padding:16px 6px;cursor:pointer;transition:.16s;}
.ps-opt:hover{border-color:var(--brass);background:rgba(201,162,75,.06);transform:translateY(-2px);}
.ps-opt:focus-visible{outline:2px solid var(--brass);outline-offset:2px;}
.ps-dot{width:26px;height:26px;border-radius:50%;border:1.5px solid var(--muted);display:grid;place-items:center;
  font-size:12px;transition:.16s;}
.ps-opt:hover .ps-dot{border-color:var(--brass);background:var(--brass);color:#1a1206;}
.ps-opt-lbl{font-size:11px;line-height:1.3;text-align:center;white-space:pre-line;color:var(--muted);}
.ps-card{background:linear-gradient(160deg,#f7f2e6 0%,#efe7d4 100%);border-radius:6px;
  box-shadow:0 30px 60px -20px rgba(0,0,0,.6),0 0 0 1px rgba(0,0,0,.05);position:relative;overflow:hidden;}
.ps-bar-track{height:5px;background:rgba(255,255,255,.06);border-radius:3px;overflow:hidden;}
.ps-bar-fill{height:100%;background:linear-gradient(90deg,var(--brass),#e3c477);border-radius:3px;transition:width .9s ease;}
.ps-axis{display:flex;align-items:center;gap:10px;font-size:12px;}
.ps-glyph path{stroke:#1c1a15;stroke-width:1.35;fill:none;stroke-linecap:round;stroke-linejoin:round;}
.ps-range{-webkit-appearance:none;appearance:none;height:4px;border-radius:3px;background:rgba(236,228,211,.14);outline:none;}
.ps-range::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:var(--brass);cursor:pointer;border:2px solid #1a1206;}
.ps-range::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--brass);cursor:pointer;border:2px solid #1a1206;}
.ps-hidden-draw path{stroke-dashoffset:var(--len);}
@media (max-width:560px){.ps-opt-lbl{display:none;}.ps-opt{padding:14px 4px;}}
@media (prefers-reduced-motion:reduce){.ps-glyph path{transition:none!important;stroke-dashoffset:0!important;}}
`;

function Glyph({ strokes, animate }) {
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    if (!animate) { setDrawn(true); return; }
    setDrawn(false);
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setDrawn(true)));
    return () => cancelAnimationFrame(id);
  }, [strokes, animate]);
  return (
    <svg className="ps-glyph" viewBox="0 0 600 600" width="100%" style={{ display: "block" }}>
      {strokes.map((s, i) => {
        const len = strokeLen(s) + 4;
        return (
          <path key={i} d={toPathD(s)}
            style={{
              strokeDasharray: len,
              strokeDashoffset: drawn ? 0 : len,
              transition: animate ? `stroke-dashoffset .75s ease ${i * 14}ms` : "none",
            }} />
        );
      })}
    </svg>
  );
}

function Bar({ label, value }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 5 }}>
        <span>{label}</span><span className="ps-mono ps-muted">{Math.round(value)}</span>
      </div>
      <div className="ps-bar-track"><div className="ps-bar-fill" style={{ width: `${value}%` }} /></div>
    </div>
  );
}

export default function PersonalitySignature() {
  const [screen, setScreen] = useState("intro"); // intro | quiz | result
  const [answers, setAnswers] = useState(Array(QUESTIONS.length).fill(null));
  const [qi, setQi] = useState(0);
  const [complexity, setComplexity] = useState(0.7); // 문양 복잡도(화려함 ↔ 그리는 시간)

  const result = useMemo(() => {
    if (answers.some((a) => a === null)) return null;
    return analyze(answers);
  }, [answers]);
  const strokes = useMemo(() => {
    if (!result) return [];
    return generateGlyph(result.type, result.vector, result.seed, complexity);
  }, [result, complexity]);

  // 로봇 펜플로터 비용 추정 (명함 90mm 폭, 40mm/s, 펜 들기 0.25s 가정)
  const stats = useMemo(() => {
    if (!strokes.length) return null;
    let len = 0;
    for (const s of strokes) len += strokeLen(s);
    const mm = len * (90 / 600);
    const lifts = strokes.length;
    const sec = mm / 40 + lifts * 0.25;
    return { lifts, mm: Math.round(mm), sec: Math.round(sec) };
  }, [strokes]);

  const pick = (val) => {
    const next = [...answers]; next[qi] = val; setAnswers(next);
    if (qi < QUESTIONS.length - 1) setTimeout(() => setQi(qi + 1), 160);
    else setTimeout(() => setScreen("result"), 200);
  };
  const restart = () => { setAnswers(Array(QUESTIONS.length).fill(null)); setQi(0); setScreen("intro"); };

  return (
    <div className="ps-root">
      <style>{CSS}</style>
      <div className="ps-wrap">

        {/* ── 인트로 ── */}
        {screen === "intro" && (
          <div style={{ textAlign: "center", paddingTop: 30 }}>
            <div className="ps-eyebrow">Personality Signature</div>
            <h1 className="ps-title" style={{ fontSize: "clamp(34px,7vw,58px)", margin: "22px 0 18px" }}>
              나를 닮은<br />단 하나의 문양
            </h1>
            <p className="ps-muted" style={{ maxWidth: 440, margin: "0 auto 34px", lineHeight: 1.75, fontSize: 15 }}>
              스물두 개의 질문에 답하면, 당신의 성향이 좌표가 되어
              세상에 하나뿐인 문양으로 새겨집니다. 로봇이 이 문양을 카드에 직접 그려 드립니다.
            </p>
            <button className="ps-btn ps-primary" onClick={() => { restartState(); setScreen("quiz"); }}>
              시작하기
            </button>
          </div>
        )}

        {/* ── 설문 ── */}
        {screen === "quiz" && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <span className="ps-eyebrow">질문 {qi + 1} / {QUESTIONS.length}</span>
              <span className="ps-mono ps-muted" style={{ fontSize: 12 }}>{QUESTIONS[qi].tag}</span>
            </div>
            <div className="ps-bar-track" style={{ marginBottom: 46 }}>
              <div className="ps-bar-fill" style={{ width: `${((qi) / QUESTIONS.length) * 100}%` }} />
            </div>

            <h2 className="ps-serif" style={{ fontSize: "clamp(24px,4.5vw,34px)", lineHeight: 1.4, minHeight: 96, marginBottom: 40 }}>
              {QUESTIONS[qi].text}
            </h2>

            <div style={{ display: "flex", gap: 8 }}>
              {SCALE.map((lbl, i) => (
                <button key={i} className="ps-opt" onClick={() => pick(i + 1)} aria-label={`${i + 1}점 ${lbl.replace("\n", " ")}`}>
                  <span className="ps-dot ps-mono">{i + 1}</span>
                  <span className="ps-opt-lbl">{lbl}</span>
                </button>
              ))}
            </div>

            <div style={{ marginTop: 34, display: "flex", justifyContent: "space-between" }}>
              <button className="ps-btn" style={{ visibility: qi > 0 ? "visible" : "hidden" }}
                onClick={() => setQi(qi - 1)}>← 이전</button>
              <button className="ps-btn" onClick={restart}>처음으로</button>
            </div>
          </div>
        )}

        {/* ── 결과 ── */}
        {screen === "result" && result && (
          <div>
            <div style={{ textAlign: "center", marginBottom: 26 }}>
              <div className="ps-eyebrow">Your Signature</div>
              <h2 className="ps-title" style={{ fontSize: "clamp(28px,5vw,42px)", margin: "12px 0 4px" }}>
                {result.type} · {FAMILY[result.type].label}
              </h2>
              <p className="ps-muted" style={{ fontSize: 14 }}>같은 유형이어도, 이 문양은 세상에 하나뿐입니다</p>
            </div>

            {/* 카드 (문양이 그려지는 순간이 주인공) */}
            <div className="ps-card" style={{ maxWidth: 440, margin: "0 auto 30px", padding: 26 }}>
              <Glyph strokes={strokes} animate />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                <span className="ps-serif" style={{ color: "#3a352a", fontSize: 20 }}>{result.type}</span>
                <span className="ps-mono" style={{ color: "#8a8371", fontSize: 11, letterSpacing: ".1em" }}>
                  #{result.seed.toString(16).slice(0, 8).toUpperCase()}
                </span>
              </div>
            </div>

            {/* 성향 벡터 + MBTI 축 */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 30, marginBottom: 34 }}>
              <div>
                <div className="ps-eyebrow" style={{ marginBottom: 16 }}>성향 벡터</div>
                <Bar label="창의성" value={result.vector.creativity} />
                <Bar label="계획성" value={result.vector.planning} />
                <Bar label="사교성" value={result.vector.sociability} />
                <Bar label="도전성" value={result.vector.challenge} />
                <Bar label="집중력" value={result.vector.focus} />
                <Bar label="감수성" value={result.vector.sensitivity} />
              </div>
              <div>
                <div className="ps-eyebrow" style={{ marginBottom: 16 }}>MBTI 좌표</div>
                {[["E", "I", result.axes.EI], ["N", "S", result.axes.NS], ["T", "F", result.axes.TF], ["J", "P", result.axes.JP]].map(([a, b, v], i) => (
                  <div key={i} className="ps-axis" style={{ marginBottom: 16 }}>
                    <span style={{ width: 14, textAlign: "center", color: v >= 50 ? "var(--brass)" : "var(--muted)", fontWeight: 700 }}>{a}</span>
                    <div className="ps-bar-track" style={{ flex: 1, position: "relative" }}>
                      <div style={{ position: "absolute", left: `${v}%`, top: -2, width: 2, height: 9, background: "var(--brass)", transform: "translateX(-1px)" }} />
                    </div>
                    <span style={{ width: 14, textAlign: "center", color: v < 50 ? "var(--brass)" : "var(--muted)", fontWeight: 700 }}>{b}</span>
                  </div>
                ))}
                <p className="ps-muted" style={{ fontSize: 12, lineHeight: 1.7, marginTop: 6 }}>
                  MBTI 유형 → 외곽 형태 · 창의성 → 대칭 차수 · 계획성 → 정갈함 · 사교성 → 크기 · 도전성 → 뾰족함 · 집중력 → 링 밀도 · 감수성 → 물결 진폭
                </p>
              </div>
            </div>

            {/* 복잡도 조절 + 플로터 비용 */}
            <div style={{ maxWidth: 440, margin: "0 auto 24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                <span className="ps-eyebrow">문양 복잡도</span>
                <span className="ps-mono ps-muted" style={{ fontSize: 12 }}>{Math.round(complexity * 100)}</span>
              </div>
              <input type="range" min="0.2" max="1" step="0.05" value={complexity} className="ps-range"
                onChange={(e) => setComplexity(parseFloat(e.target.value))} style={{ width: "100%" }} />
              {stats && (
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14, fontSize: 12 }}>
                  <span className="ps-muted">펜 들기 <b className="ps-mono" style={{ color: "var(--ink)" }}>{stats.lifts}</b>회</span>
                  <span className="ps-muted">총 선 <b className="ps-mono" style={{ color: "var(--ink)" }}>{stats.mm}</b>mm</span>
                  <span className="ps-muted">예상 <b className="ps-mono" style={{ color: "var(--ink)" }}>~{stats.sec}</b>초</span>
                </div>
              )}
              <p className="ps-muted" style={{ fontSize: 11, marginTop: 6, textAlign: "center" }}>
                명함 90mm · 펜 속도 40mm/s 가정 · 필러 링은 한 붓이라 펜 들기 없이 밀도만 올립니다
              </p>
            </div>

            {/* 내보내기 */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
              <button className="ps-btn ps-primary" onClick={() => download(`signature_${result.type}.svg`, toSVG(strokes, { type: result.type }), "image/svg+xml")}>
                SVG 내려받기
              </button>
              <button className="ps-btn" onClick={() => download(`signature_${result.type}.json`, toRobotJSON(strokes, { type: result.type, vector: result.vector, axes: result.axes }), "application/json")}>
                로봇용 폴리라인(JSON)
              </button>
              <button className="ps-btn" onClick={restart}>다시 하기</button>
            </div>
            <p className="ps-muted" style={{ textAlign: "center", fontSize: 11, marginTop: 20 }}>
              폴리라인 {strokes.length}획 · 로봇 JSON은 획 순서 그대로 펜다운/펜업 경로가 됩니다
            </p>
          </div>
        )}
      </div>
    </div>
  );

  function restartState() { setAnswers(Array(QUESTIONS.length).fill(null)); setQi(0); }
}
