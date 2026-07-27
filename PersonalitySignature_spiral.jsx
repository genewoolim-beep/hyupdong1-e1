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

  // 성향 벡터 4종 (0~100) — 문양 조형 파라미터로 쓰인다.
  // [간소화 2026-07-23] 기존 6종(창의성·계획성·사교성·도전성·집중력·감수성)을 의미가 가까운
  // 것끼리 묶어 4종으로 줄였다. 문항 구성은 그대로 재사용(문항 자체를 더 늘리진 않음).
  //   창의성 = 기존 창의성 + 도전성  (둘 다 "새로움을 향한 개방성" 계열 — 직관·상상·발상 +
  //            위험을 감수한 도전·즉흥. 문양에서도 원래 같이 N·ratio 를 결정해 자연스럽게 묶임)
  //   몰입도 = 기존 집중력 + 계획성  (둘 다 "질서·지속성" 계열 — 몰입·막판집중 + 계획·여유·규칙.
  //            문양에서도 layers·dTheta 를 함께 결정)
  //   사교성 · 감수성은 그대로 유지(다른 벡터와 의미가 안 겹쳐 합칠 이유가 없음).
  const vector = {
    creativity: 100 * mean(nz(6), nz(7), nz(8), nz(21), nz(19)),   // 직관·상상·발상 + 도전·즉흥
    focus: 100 * mean(nz(22), nz(20), nz(16), nz(17), nz(18)),     // 몰입·막판집중 + 계획·여유·규칙
    sociability: 100 * mean(nz(1), nz(2), inv(nz(3))),             // 활력·교류·고독역
    sensitivity: 100 * mean(nz(14), nz(15), inv(nz(13))),          // 공감·감성 + 원칙역채점
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
// circlePts에 cos(N·(a+π/2)) 물결을 살짝 얹은 버전. 회전이 아니라 대칭적 굴곡이라 좌우대칭이
// 항상 유지된다(계획성이 낮을수록 손으로 그린 듯 살짝 일그러진 원, 높으면 원본처럼 완벽한 정원).
function circlePtsWavy(cx, cy, r, N, amp, n = 160) {
  if (amp <= 0.001) return circlePts(cx, cy, r, n);
  const p = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI;
    const rr = r * (1 + amp * Math.cos(N * (a + Math.PI / 2)));
    p.push(polar(cx, cy, a, rr));
  }
  return p;
}


/* ────────────────────────────────────────────────────────────
   4. MBTI 16종 → 모티프 매칭
   각 유형은 label(결과화면 표시명)과 motif(6절 문양 생성기의 빌더 키)로 구성.
   16종 전부 나선 계열(SPIRAL_SIL 로 makeShape 실루엣 매핑) 하나로 통일한다.
   E 8종은 뒤 3글자(N·S/T·F/J·P)가 같은 I 유형과 motif를 그대로 공유한다.
   몰입도·사교성은 generateGlyph에서 I/E 각자의 하위 구간으로 선형 매핑해 넣는다
   (I: 몰입50~100/사교0~50 · E: 몰입0~50/사교50~100) — 슬라이더를 올리면 I/E 둘 다
   항상 같은 방향으로 반응하고(반전 아님), 슬라이더 전 구간에서 죽는 부분 없이
   계속 반응하면서도 같은 슬라이더 값에서 E가 항상 더 크고 성글게 나온다.
──────────────────────────────────────────────────────────── */
// [2026-07-25 재설계 → 같은 날 재통합] 애초엔 I=나선(내향)/E=기하(외향)로 나눴었으나,
// geoGlyph 계열은 걷어내고 16종 전부 spiralGlyph 하나로 합쳤다. I/E 차이는 처음엔
// 몰입도·사교성을 통째로 거울반전(100−값)했는데 슬라이더를 올려도 E는 반대로 반응해
// 헷갈렸고, 그다음엔 고정 오프셋(±50)을 더하고 clamp했는데 이번엔 슬라이더 절반
// 구간이 0/100에 눌어붙어 그 구간에서 전혀 안 바뀌는 "죽은 구간"이 생겼다 → clamp
// 대신 0~100 입력 전체를 I/E 각자의 하위 구간에 선형으로 늘려 매핑해서 해결.
// geoGlyph()/그 전용 헬퍼(triangleRing·circlePtsWavy·petalOutline)는 되돌릴 경우를 대비해
// 코드에는 남겨뒀지만 더는 호출되지 않는다.
const FAMILY = {
  // I — 나선 8종 (회전+축소, 감김리듬은 기질군 RHYTHM 승계)
  INTJ: { label: "결정 나선", motif: "crystalFermat" },
  INTP: { label: "불규칙 결정 나선", motif: "crystalDrift" },
  INFJ: { label: "별사면체 나선", motif: "starTetraSpiral" },
  INFP: { label: "잎맥 물결", motif: "leafCurrent" },
  ISTJ: { label: "사각 나선", motif: "squareSpiral" },
  ISFJ: { label: "조가비 나선", motif: "shellGuard" },
  ISTP: { label: "육각 나선", motif: "hexSpiral" },
  ISFP: { label: "흩날린 꽃잎", motif: "petalDrift" },
  // E — I와 동일 motif(뒤 3글자 매칭), 몰입도/사교성은 I와 반대쪽 하위 구간으로 매핑
  ENTJ: { label: "결정 나선", motif: "crystalFermat" },
  ENTP: { label: "불규칙 결정 나선", motif: "crystalDrift" },
  ESTJ: { label: "사각 나선", motif: "squareSpiral" },
  ESTP: { label: "육각 나선", motif: "hexSpiral" },
  ENFJ: { label: "별사면체 나선", motif: "starTetraSpiral" },
  ENFP: { label: "잎맥 물결", motif: "leafCurrent" },
  ESFJ: { label: "조가비 나선", motif: "shellGuard" },
  ESFP: { label: "흩날린 꽃잎", motif: "petalDrift" },
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

// 마디 위의 작은 십자 눈금(조준선). 원(구슬)과 달리 뭉쳐 보이지 않아 "정밀함/집중"을 표현하기에
// 더 낫다. len=0이면 아무것도 그리지 않는다(값이 낮을 때 화면에 아무 잔상도 남지 않음).
function bTick(cx, cy, R, N, off, len) {
  if (len <= 0.01) return [];
  const out = [];
  for (let k = 0; k < N; k++) {
    const a = (k * 2 * Math.PI) / N - Math.PI / 2 + off;
    const c = polar(cx, cy, a, R);
    const px = Math.cos(a + Math.PI / 2), py = Math.sin(a + Math.PI / 2);
    out.push([[c[0] - px * len, c[1] - py * len], [c[0] + px * len, c[1] + py * len]]);
    out.push([[c[0] - Math.cos(a) * len, c[1] - Math.sin(a) * len], [c[0] + Math.cos(a) * len, c[1] + Math.sin(a) * len]]);
  }
  return out;
}

// 방사살: N개 반경선
function bSpoke(cx, cy, rIn, rOut, N, off = 0) {
  const out = [];
  for (let k = 0; k < N; k++) {
    const a = (k * 2 * Math.PI) / N - Math.PI / 2 + off;
    out.push([polar(cx, cy, a, rIn), polar(cx, cy, a, rOut)]);
  }
  return out;
}

// 나침반형 컴퍼스 별(뾰족 끝 arms개 + 골 arms개, 직선 연결). sharp↑ → 골이 더 깊어져 더 뾰족해짐.
// sharp=0.5(기본값)에서 기초 이미지와 동일한 골/끝 비율(≈0.32)이 나오도록 맞춤.
function bBurst(cx, cy, outerR, arms, sharp, off, loRatio = 0.45, hiRatio = 0.20) {
  const innerR = outerR * map(sharp, 0, 1, loRatio, hiRatio);
  const pts = [];
  const total = arms * 2;
  for (let i = 0; i <= total; i++) {
    const a = (i * Math.PI) / arms - Math.PI / 2 + off;
    pts.push(polar(cx, cy, a, i % 2 === 0 ? outerR : innerR));
  }
  return [pts];
}

// 결정(크리스탈) 패싯: N개 다이아몬드형 조각. 항상 원본 기초 이미지와 동일한 완전 직선
// 형태(둥글어지는 연출 없음). sharp↑ → 폭이 좁아져 더 예리해짐. loRatio/hiRatio로 유형별
// 기초 이미지의 폭 비율에 맞춘다(기본값은 INTJ 결정 성좌 비율).
function bFacet(cx, cy, rBase, rTip, N, sharp, off, loRatio = 0.38, hiRatio = 0.22) {
  const out = [];
  const halfW = (rTip - rBase) * map(sharp, 0, 1, loRatio, hiRatio);
  const midR = rBase + (rTip - rBase) * 0.5;
  for (let k = 0; k < N; k++) {
    const ang = (k * 2 * Math.PI) / N - Math.PI / 2 + off;
    const px = Math.cos(ang + Math.PI / 2), py = Math.sin(ang + Math.PI / 2);
    const base = polar(cx, cy, ang, rBase), tip = polar(cx, cy, ang, rTip);
    const sideL = [cx + Math.cos(ang) * midR + px * halfW, cy + Math.sin(ang) * midR + py * halfW];
    const sideR = [cx + Math.cos(ang) * midR - px * halfW, cy + Math.sin(ang) * midR - py * halfW];
    out.push([base, sideL, tip, sideR, base]);
  }
  return out;
}

// N각형 격자 + 마주보는 꼭짓점을 잇는 대각선(짝수 N일 때만). 성좌/격자 중심부의 "짜임" 표현.
// withDiagonals=false면 순수 다각형 윤곽만(장식용 테두리 링). skipOne=true면 INTJ 기초 이미지처럼
// 대각선 중 수평에 가장 가까운 것 하나를 의도적으로 비워둔다(INTP는 전부 그린다: skipOne=false).
function bLattice(cx, cy, R, N, off, withDiagonals = true, skipOne = true) {
  const v = [];
  for (let k = 0; k < N; k++) v.push(polar(cx, cy, (k * 2 * Math.PI) / N - Math.PI / 2 + off, R));
  const out = [v.concat([v[0]])];
  if (withDiagonals && N % 2 === 0) {
    const skip = skipOne ? Math.round(N / 4) % (N / 2) : -1;
    for (let k = 0; k < N / 2; k++) {
      if (k === skip) continue;
      out.push([v[k], v[k + N / 2]]);
    }
  }
  return out;
}

// 마디(구슬)에서 옆 패싯의 밑변 꼭짓점(스포크가 닿는 자리, 이미 그려져 있는 확실한 지점)까지
// 항상 끝까지 이어지는 성좌 연결 곡선(2차 베지어). N개. bow=0이면 거의 직선(정갈한 목걸이 고리),
// bow가 커질수록 바깥으로 크게 부풀려 휘어진다(표현적).
function bArcLink(cx, cy, rStart, rEnd, N, off, bow = 0.5) {
  const out = [];
  const gap = (2 * Math.PI) / N;
  for (let k = 0; k < N; k++) {
    const a0 = k * gap - Math.PI / 2 + off;
    const a1 = a0 + gap;
    const p0 = polar(cx, cy, a0, rStart);
    const p1 = polar(cx, cy, a1, rEnd);
    const midAng = a0 + gap * 0.5;
    const midR = ((rStart + rEnd) / 2) * (1 + bow * 0.4);
    const ctrl = polar(cx, cy, midAng, midR);
    out.push(quad(p0, ctrl, p1, 16));
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
    case "hexagon": raw = polygonRaw(ci(N, 5, 9), { rot: -Math.PI / 2 }); break;
    case "hexagon6": raw = polygonRaw(6, { rot: -Math.PI / 2 }); break;   // 고정 정육각(N 무관, hex_spiral.svg 원본과 동일)
    case "square4":  raw = polygonRaw(4, { rot: -Math.PI / 4 }); break;   // 고정 정사각(축정렬, spiral_squares.svg 원본과 동일)
    case "triUp":    raw = polygonRaw(3, { rot: -Math.PI / 2 }); break;   // 별사면체용 위삼각(꼭짓점 위)
    case "triDown":  raw = polygonRaw(3, { rot: Math.PI / 2 }); break;    // 별사면체용 아래삼각(꼭짓점 아래)
    case "diamond": raw = polygonRaw(4, { rot: -Math.PI / 2, stretchY: 1.28 }); break;
    case "gear":    raw = gearRaw(ci(N, 10, 16)); break;
    // wave/blossom/bud/crystal/star12은 |cos|·|sin|을 쓰는 superformula(또는 그와 같은 구조의
    // waveRaw) 특성상 자기 좌표계에서 항상 "가로축(x축)" 기준으로만 좌우대칭이라, m(대칭수)이
    // 홀수면 회전 없이는 세로축(진짜 좌우) 대칭이 깨진다(예: N/2가 홀수로 반올림되는 경우가
    // 흔함). 90도 돌리면 그 가로축 대칭이 세로축 대칭으로 바뀌는데, 이 성질은 m의 홀짝과
    // 무관하게 항상 성립해서(직접 수치 검증함) 모든 경우에 안전하게 좌우대칭을 보장한다.
    case "wave":    raw = rotateRaw(waveRaw(ci(N, 8, 14), 0.12), Math.PI / 2); break;
    case "blossom": raw = rotateRaw(superRaw({ m: ci(N / 2, 4, 8), n1: 1, n2: 1.7, n3: 1.7 }), Math.PI / 2); break;
    case "bud":     raw = rotateRaw(superRaw({ m: 5, n1: 1, n2: 1.8, n3: 1.8 }), Math.PI / 2); break;
    case "crystal": raw = rotateRaw(superRaw({ m: ci(N / 2, 5, 8), n1: 0.35, n2: 0.4, n3: 0.4 }), Math.PI / 2); break;
    case "star12":  raw = rotateRaw(superRaw({ m: ci(N, 10, 16), n1: 0.5, n2: 0.6, n3: 0.6 }), Math.PI / 2); break;
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
// N/amp를 주면 반경에 cos(N·(θ+π/2)) 물결을 살짝 얹는다. π/2 위상 보정 덕분에 N의 홀/짝 여부와
// 무관하게 항상 좌우대칭이 유지된다(회전이 아니라 대칭적인 굴곡이라 좌우가 절대 어긋나지 않음).
function shapeRing(shape, cx, cy, s, N = 0, amp = 0) {
  return shape.polar.map(([th, rho]) => {
    const rr = rho * s * (amp ? 1 + amp * Math.cos(N * (th + Math.PI / 2)) : 1);
    return [cx + Math.cos(th) * rr, cy + Math.sin(th) * rr];
  });
}
// 형태 반경에 N겹 cos 물결을 얹은 기요셰 링(형태를 따라감)
function shapeRipple(shape, cx, cy, s, N, amp, off) {
  return shape.polar.map(([th, rho]) => {
    const rr = rho * s * (1 + amp * Math.cos(N * th + off));
    return [cx + Math.cos(th) * rr, cy + Math.sin(th) * rr];
  });
}

/* ────────────────────────────────────────────────────────────
   6. 문양 생성기 — 16종 전부 나선(spiralGlyph) (2026-07-25 재설계 → 같은 날 재통합)
   3층 구조:
     [1층] I/E         → 같은 motif(뒤 3글자 매칭)를 공유하고, 몰입도·사교성을
                         각자의 하위 구간(50~100/0~50, 반대로 0~50/50~100)에 선형
                         매핑한다 — 반응 방향·전 구간 반응성은 I/E 공통, 크기만 다름.
     [2층] N·S/T·F/J·P → 유형 고정 스타일(라운딩·구조선·지터·열린획) + 기질군 감김리듬
     [3층] 성향벡터 4종 → 같은 유형 안의 개인차(연속값: N·겹수·크기·물결)
   신성기하학 상징(메르카바·스리얀트라·베시카·Seed/Flower of Life·토러스)은
   "구성 원리"만 차용해 자체 알고리즘으로 생성(형태 복제 아님).
   로봇 제약: 모든 획=긴 폴리라인(점찍기 금지) · 총 획수 ≤ ~25 ·
             MIN_RATIO floor 로 중심부 급곡률 방지(한 점으로 수렴 금지).
   ※ geoGlyph()(아래)는 E가 "기하" 계열을 쓰던 이전 설계의 유산으로, 더는 호출되지
     않는다(되돌릴 경우를 대비해 남겨둠).
──────────────────────────────────────────────────────────── */
function temperamentOf(type) {
  const isN = type[1] === "N", isT = type[2] === "T";
  return isN ? (isT ? "NT" : "NF") : (isT ? "ST" : "SF");
}
// 기질군별 감김/중첩 리듬(구 GROWTH_FAMILY 승계·확장) — 층간 반지름 수열의 곡선 모양.
const RHYTHM = { NT: "fermat", NF: "log", ST: "archimedean", SF: "osc" };
const MIN_RATIO = 0.14;   // 중심부 최소 반지름 비율 — 로봇 급곡률 방지 floor
// k번째 층 스케일(1 → endScale). endScale 을 floor 위로 클램프한 뒤, 각 리듬은
// "거기 도달하는 곡선 모양"만 다르게 한다(종착점 동일 → 퍼짐 정도는 ratio 가 일관 결정).
function rhythmScale(rhythm, k, layers, ratio) {
  const t = layers > 1 ? k / (layers - 1) : 0;
  const endScale = Math.max(Math.pow(ratio, layers - 1), MIN_RATIO);
  let sc;
  if (rhythm === "archimedean") sc = 1 + (endScale - 1) * t;                 // 등간격(나이테)
  else if (rhythm === "fermat") sc = 1 + (endScale - 1) * Math.pow(t, 1.8);  // 바깥 성김→중심 응축
  else if (rhythm === "osc") sc = Math.pow(endScale, t) * (1 + 0.14 * Math.cos(3.5 * Math.PI * t)); // 파동(조가비)
  else sc = Math.pow(endScale, t);                                           // log(자기유사·황금)
  return Math.max(MIN_RATIO * 0.92, Math.min(1.04, sc));
}
// [2층] 뒤 3글자 → 유형 고정 스타일. N/S 는 모티프 자체(곡선계 vs 직선계)에 이미 반영돼
// 있어 여기서는 T/F(구조선·라운딩)와 J/P(균일 vs 지터·열린획)만 다룬다.
function letterStyle(type) {
  const T = type[2] === "T", P = type[3] === "P";
  return {
    waveBase: T ? 0 : 0.009,       // F: 기본 라운딩 물결
    waveSpan: T ? 0.012 : 0.032,   // 감수성이 물결에 기여하는 최대폭(T는 상한 축소) — 최대치가 너무 심하게 휘어 보여 축소(기존 0.02/0.055)
    structOn: T,                   // T: 구조선(현·스포크) 추가
    spacingJitter: P ? 0.045 : 0,  // P: 층 간격 지터(seed 기반 → 같은 응답=같은 문양)
    openStroke: P,                 // P: 일부 획 끝을 열어 미완의 개방감
  };
}
// [3층] 성향벡터 → 연속 파라미터.
//   creativity → 대칭차수 N·퍼짐(ratio)   focus → 겹수·감김세기/구조선밀도
//   sociability → 전체 크기   sensitivity → 물결(호출측에서 p.wave 로 주입)
function mapVectors(V, fam, flavor, complexity) {
  const N = Math.max(4, Math.min(14, Math.round(map(V.creativity, 0, 100, 6, 12)) + flavor.nNudge));
  const outerR = map(V.sociability, 0, 100, 205, 275);
  let layers, dTheta, ratio, structDensity;
  if (fam === "spiral") {
    // 몰입도 폭을 조금 더 넓혀(겹수 11~20→9~22, 회전각 12~5°→14~3°) 몰입도 차이에
    // 따른 문양 차이가 더 뚜렷하게 드러나도록 함.
    layers = Math.round(map(V.focus, 0, 100, 9, 22) * (0.62 + 0.5 * complexity));
    layers = Math.max(7, Math.min(22, layers));
    dTheta = map(V.focus, 0, 100, 14, 3) * Math.PI / 180 * flavor.thetaMul;
    ratio = map(V.creativity, 0, 100, 0.93, 0.965);
    structDensity = 0;
  } else {
    layers = Math.round(map(V.focus, 0, 100, 3.4, 6.6) * (0.72 + 0.4 * complexity));
    layers = Math.max(3, Math.min(8, layers));
    dTheta = 0;
    ratio = map(V.creativity, 0, 100, 0.78, 0.90);
    structDensity = Math.round(map(V.focus, 0, 100, 2, 6));
  }
  return { N, outerR, layers, dTheta, ratio, structDensity };
}
// 유형 해시 고정 변주(승계) — 같은 계열·같은 리듬 유형끼리도 항상 갈리게.
function typeFlavor(type) {
  // 앞글자(I/E)는 해시에서 뺀다 — 뒤 3글자(N·S/T·F/J·P)가 같은 I/E 짝(예: INTJ·ENTJ)이
  // 완전히 같은 flavor(눌러늘임·감김속도)를 공유하게 해서, 미리보기에서 두 짝이 나란히
  // 있을 때 크기(오프셋)만 다르고 형태·방향은 정렬되어 보인다.
  const h = hashInts(type.slice(1).split("").map((c) => c.charCodeAt(0)));
  const r = mulberry32(h);
  return {
    squeeze: 0.86 + r() * 0.28,          // 실루엣 눌러늘임
    rotBase: 0,                          // 회전기준 고정(모든 유형이 같은 방향으로 시작 → 대칭·정렬된 인상)
    nNudge: Math.round((r() - 0.5) * 4), // -2~+2
    thetaMul: 0.6 + r() * 1.0,           // 감김 속도 배율
  };
}

// ── 공용 헬퍼 ──────────────────────────────────────────────
function ringOf(shapePolar, cx, cy, sc, rot, wave, N, squeeze) {
  return shapePolar.map(([th, rho]) => {
    const rr = rho * sc * (1 + (wave ? wave * Math.cos(N * (th + Math.PI / 2)) : 0));
    return [cx + Math.cos(th + rot) * rr, cy + Math.sin(th + rot) * rr * squeeze];
  });
}
function trimEnds(pts, frac) {   // P: 획 양끝을 잘라 "열린 획"으로
  const cut = Math.max(1, Math.floor(pts.length * frac));
  return pts.slice(cut, pts.length - cut);
}
function lineStroke(a, b, seg = 12) {
  const p = [];
  for (let i = 0; i <= seg; i++) { const t = i / seg; p.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]); }
  return p;
}
function triangleRing(cx, cy, r, up = true) {
  const rot = up ? -Math.PI / 2 : Math.PI / 2;
  return polygonRaw(3, { rot }).map(([x, y]) => [cx + x * r, cy + y * r]);
}
// ── I 계열: 나선 8종 (모티프 → makeShape 실루엣, 층마다 회전+축소) ────────
const SPIRAL_SIL = {
  crystalFermat: "crystal",  // INTJ — 결정면이 중심으로 응축(fermat)
  crystalDrift: "crystal",   // INTP — INTJ와 같은 결정 실루엣이지만 층마다 회전이 들쭉날쭉(아래 참고)
  hexSpiral: "hexagon6",     // ISTP — samples/hex_spiral.svg 와 같은 정육각 회전축소 나선
  petalDrift: "bud",         // ISFP — 흩날린 꽃잎(열린 획)
  squareSpiral: "square4",   // ISTJ — samples/spiral_squares.svg 와 같은 정사각 회전축소 나선
  shellGuard: "wave",        // ISFJ — 조가비 파동 나선
  // starTetraSpiral(INFJ)은 층마다 삼각형이 위/아래로 번갈아 뒤집히므로(별사면체=메르카바
  // 원리) 고정 sil 하나로 안 되고 spiralGlyph 안에서 직접 triUp/triDown 두 형태를 골라 쓴다.
  leafCurrent: "leaf",       // INFP — 잎맥 물결 나선
};
// 열린 획(trimEnds로 층 일부를 끊어 미완의 개방감을 주는 openStroke 연출)을 절대 쓰지 않을
// 모티프 — 육각/별사면체/잎맥/흩날린꽃잎/조가비는 끊긴 구간 없이 항상 완전히 이어지게 한다.
const NEVER_OPEN_MOTIFS = new Set([
  "hexSpiral", "starTetraSpiral", "leafCurrent", "petalDrift", "shellGuard",
]);
function spiralGlyph(motif, p, rhythm, style, flavor, rng, cx, cy) {
  const sil = SPIRAL_SIL[motif] || "circle";
  const wave = style.waveBase + p.wave;
  let layers = p.layers;
  let dTheta = p.dTheta;
  let rotJitter = 0;
  if (motif === "crystalFermat") {
    // 결정 실루엣은 스파이크 골이 깊어, 회전이 크면 골끼리 겹쳐 중심이 뭉개진다.
    // 회전을 확 줄여(결정면이 거의 정렬된 채 살짝 비틀림) fermat 응축이 읽히게 한다.
    dTheta *= 0.3;
    layers = Math.min(layers, 12);
  } else if (motif === "crystalDrift") {
    // INTP/ENTP — INTJ(crystalFermat)는 결정면이 가지런히 정렬되지만, 이쪽은 층마다 회전에
    // 무작위 흔들림(rotJitter)을 더해 결정이 들쭉날쭉 삐쳐 자란 것처럼 불규칙하게 뻗어나가게 한다.
    // dTheta를 몰입도의 I/E 가족별 리매핑값(p.dTheta) 그대로 두면 E는 항상 dTheta가 더 커서
    // (몰입도가 낮은 쪽 구간에 매핑되므로) 같은 rotJitter라도 상대적으로 덜 두드러져 ENTP가
    // INTP보다 덜 불규칙해 보인다 — 그래서 이 모티프만 몰입도·가족과 무관한 고정 dTheta를
    // 써서 I/E 둘 다 지터의 지배력이 똑같이 커 보이게 한다.
    layers = Math.min(layers, 16);
    dTheta = 0.1 * flavor.thetaMul;
    rotJitter = 0.45;
  } else if (motif === "leafCurrent") {
    // 잎(렌즈꼴)을 작은 회전으로 겹치면 엉킨 눈(目) 모양이 된다. 실제 식물의 잎차례
    // (phyllotaxis)처럼 황금각(137.5°)씩 돌리면 해바라기식 잎 로제트가 된다 —
    // "잎맥 물결"의 상징(자연·감각)에도 정확히 부합. thetaMul 로 유형 결만 살짝 가감.
    dTheta = 2.39996 * (0.97 + 0.06 * (flavor.thetaMul - 1.1));
  } else if (motif === "starTetraSpiral") {
    // 층마다 돌리면 삼각형 변끼리 계속 어긋나며 지저분해 보인다("나선"이 이 모티프엔 안 맞음).
    // 회전을 0으로 고정해 위/아래 삼각이 층마다 정확히 같은 자리에서 겹치는 하나의 별사면체
    // 문양 안에, 크기만 다른 겹(층)이 쌓이는 방식으로 바꾼다(겹겹의 메르카바).
    dTheta = 0;
  }
  const shape = makeShape(sil, cx, cy, p.outerR, p.N);
  // 별사면체(메르카바) 나선: 층마다 위/아래 삼각을 번갈아 써서, 회전+축소되며 겹치는 동안
  // 두 삼각이 계속 엇갈려 스치는 것이 마치 삼각형 2개가 맞물려 도는 것처럼 읽힌다.
  const shapeUp = motif === "starTetraSpiral" ? makeShape("triUp", cx, cy, p.outerR, p.N) : null;
  const shapeDown = motif === "starTetraSpiral" ? makeShape("triDown", cx, cy, p.outerR, p.N) : null;
  // rot0을 고정값(flavor.rotBase=0)으로 둔다 — 여기에 무작위 회전을 더하면 실루엣 자체는
  // 좌우대칭이어도 그 대칭축이 랜덤한 방향으로 기울어 보여서 "보기 좋은 좌우대칭" 인상이
  // 깨진다. 가장 바깥(가장 크고 눈에 띄는) 층을 정확히 대칭 기준 자세로 고정해 두면, 안쪽
  // 층들이 dTheta만큼씩 감겨 들어가며 한쪽으로 살짝 치우쳐도 전체 인상은 정돈되어 보인다.
  const rot0 = flavor.rotBase;
  const strokes = [];
  for (let k = 0; k < layers; k++) {
    let sc = rhythmScale(rhythm, k, layers, p.ratio);
    if (style.spacingJitter) sc *= 1 + (rng() - 0.5) * 2 * style.spacingJitter;
    const rot = rot0 + k * dTheta + (rotJitter ? (rng() - 0.5) * 2 * rotJitter : 0);
    const layerShape = motif === "starTetraSpiral" ? (k % 2 === 0 ? shapeUp : shapeDown) : shape;
    let ring = ringOf(layerShape.polar, cx, cy, sc, rot, wave, p.N, flavor.squeeze);
    if (style.openStroke && !NEVER_OPEN_MOTIFS.has(motif) && k % 3 === 1) ring = trimEnds(ring, 0.06 + rng() * 0.06);
    strokes.push(ring);
  }
  return strokes;
}

// ── [미사용] 옛 E 계열: 기하 8종 (무회전 중첩 + 구조선) — generateGlyph가 더는 호출하지 않음 ──
function geoGlyph(motif, p, rhythm, style, flavor, rng, cx, cy) {
  const strokes = [];
  const R = p.outerR, floorR = R * MIN_RATIO;
  const scAt = (k, L) => rhythmScale(rhythm, k, L, p.ratio);
  const jit = () => (style.spacingJitter ? 1 + (rng() - 0.5) * 2 * style.spacingJitter : 1);
  const wave = style.waveBase + p.wave;

  if (motif === "crystalRadiant") {
    // ENTJ — INTJ(crystalFermat)와 같은 결정 실루엣이지만, 회전하며 안으로 감기는 대신
    // 제자리에서 겹겹이 서서 뾰족한 끝마다 중심에서 곧게 뻗는 방사살을 더한다(외향=밖으로
    // 뻗는 구조). 전체 크기도 10% 더 크게(outerR*1.1) 잡아 존재감을 키운다.
    const R2 = R * 1.1;
    const crystal = makeShape("crystal", cx, cy, R2, p.N);
    const L = Math.min(4, Math.max(2, p.layers));
    for (let k = 0; k < L; k++)
      strokes.push(ringOf(crystal.polar, cx, cy, scAt(k, L) * jit(), 0, wave, p.N, 1));
    if (style.structOn) {
      const m = Math.max(5, Math.min(8, Math.round(p.N / 2)));   // crystal 실루엣의 실제 대칭수와 일치
      for (let i = 0; i < m; i++) {
        const a = -Math.PI / 2 + (i * 2 * Math.PI) / m;
        // 방사살이 결정 끝보다 더 밖으로 삐져나오게(R2*1.3) — 중심에서 계속 뻗어나가는 느낌.
        strokes.push(lineStroke(polar(cx, cy, a, floorR), polar(cx, cy, a, R2 * 1.3)));
      }
    }
    strokes.push(circlePts(cx, cy, floorR));
  } else if (motif === "sparkLattice") {
    // ENTP — 별 윤곽 중첩 + 꼭짓점을 건너뛰며 잇는 불규칙 현(발상의 연결망, P지터).
    // 별 실루엣은 골이 깊어 rhythmScale 로 중심(0.14)까지 응축시키면 골끼리 겹쳐
    // 중앙이 까맣게 뭉친다 → 얕은 고정 수열(1, 0.82, 0.67, 0.55)로 바깥쪽만 중첩.
    const star = makeShape("crystal", cx, cy, R, p.N);
    const L = Math.min(4, p.layers);
    for (let k = 0; k < L; k++)
      strokes.push(ringOf(star.polar, cx, cy, Math.pow(0.82, k) * jit(), 0, 0, p.N, 1));
    const m = Math.max(5, Math.min(8, Math.round(p.N / 2)));   // crystal 실루엣의 실제 대칭수와 일치
    const tip = (i, r) => polar(cx, cy, -Math.PI / 2 + (i * 2 * Math.PI) / m, r);
    const chords = Math.min(p.structDensity + 2, 7);
    for (let j = 0; j < chords; j++) {
      // skip=2 고정(m이 작을 때 skip 3이면 현이 중심 근처를 지나 floor 규칙 위반), m≥7이면 가끔 3.
      const i = Math.floor(rng() * m), skip = m >= 7 && rng() < 0.5 ? 3 : 2;
      // 바깥쪽 끝을 별 꼭짓점보다 더 밖으로(R*1.18) 빼서 중심에서 더 멀리 뻗어나가는 느낌을 준다.
      strokes.push(lineStroke(tip(i, R * 1.18 * jit()), tip(i + skip, R * (0.5 + rng() * 0.35))));
    }
  } else if (motif === "axiomGrid") {
    // ESTJ — 정육각 중첩(0°/30° 교대 = 등축 격자감) + 방사 스포크(제도·구조).
    for (let k = 0; k < p.layers; k++) {
      const r = R * scAt(k, p.layers);
      strokes.push(polygonRaw(6, { rot: -Math.PI / 2 + (k % 2) * (Math.PI / 6) })
        .map(([x, y]) => [cx + x * r, cy + y * r]));
    }
    if (style.structOn)
      for (let i = 0; i < 6; i++) {
        const a = -Math.PI / 2 + (i * Math.PI) / 3;
        strokes.push(lineStroke(polar(cx, cy, a, floorR), polar(cx, cy, a, R)));
      }
  } else if (motif === "yantraDrive") {
    // ESTP — 스리얀트라 원리: 크기가 다른 위/아래 삼각의 교차 긴장 + 외곽원 + 중심 허브.
    strokes.push(circlePts(cx, cy, R));
    for (let k = 0; k < p.layers; k++)
      strokes.push(triangleRing(cx, cy, R * 0.9 * scAt(k, p.layers) * jit(), k % 2 === 1));
    strokes.push(circlePts(cx, cy, floorR));   // bindu — 한 점 대신 floor 원
  } else if (motif === "radiantVesica") {
    // ENFJ — 베시카(둘의 합일) 꽃잎 로제트 + 인도하는 방사 빛살 + 외곽원.
    // bPetal(꽃잎당 2획: 겹꽃잎)은 획수 상한을 넘기므로 홑겹 petalOutline 을 직접 사용.
    const petalN = Math.max(6, Math.min(10, p.N));
    strokes.push(circlePts(cx, cy, R));
    for (let i = 0; i < petalN; i++) {
      const ang = (i * 2 * Math.PI) / petalN - Math.PI / 2;
      strokes.push(petalOutline(cx, cy, ang, R * 0.30, R * 0.88, 0.6 + wave * 4, 0.35));
    }
    const rays = Math.min(p.structDensity + 3, 8);
    for (let i = 0; i < rays; i++) {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / rays;
      strokes.push(lineStroke(polar(cx, cy, a, R * 0.90), polar(cx, cy, a, R * 0.99)));
    }
    strokes.push(circlePts(cx, cy, R * 0.30));
  } else if (motif === "seedBurst") {
    // ENFP — Seed of Life 원리: 서로를 지나는 원들. P: 배치 지터 + 일부 원 열림(가능성).
    const n = Math.max(5, Math.min(8, Math.round(p.N * 0.7)));
    const r0 = R * 0.46;
    strokes.push(circlePts(cx, cy, r0));
    for (let i = 0; i < n; i++) {
      const c = polar(cx, cy, flavor.rotBase + (i * 2 * Math.PI) / n, r0 * jit());
      let ring = circlePts(c[0], c[1], r0 * (0.96 + (rng() - 0.5) * 0.06));
      if (style.openStroke && i % 2 === 1) ring = trimEnds(ring, 0.08);
      strokes.push(ring);
    }
    strokes.push(circlePts(cx, cy, R * 0.98));
  } else if (motif === "flowerCommons") {
    // ESFJ — Flower of Life 축소판(중심+6원, 여유 시 두 번째 고리 6원). 전부 닫힘·균일(J).
    const r0 = R * 0.34;
    strokes.push(circlePts(cx, cy, r0));
    for (let i = 0; i < 6; i++) {
      const c = polar(cx, cy, -Math.PI / 2 + (i * Math.PI) / 3, r0);
      strokes.push(circlePts(c[0], c[1], r0));
    }
    if (p.layers >= 5)
      for (let i = 0; i < 6; i++) {
        const c = polar(cx, cy, -Math.PI / 2 + Math.PI / 6 + (i * Math.PI) / 3, r0 * 1.732);
        strokes.push(circlePts(c[0], c[1], r0));
      }
    strokes.push(circlePts(cx, cy, R * 0.98));
  } else {
    // ESFP torusStage — 동심 링+스캘럽 링 교대(순환·무대 조명 리듬).
    const L = Math.max(4, p.layers + 2);
    for (let k = 0; k < L; k++) {
      const r = R * scAt(k, L);
      strokes.push(k % 2 === 0 ? circlePts(cx, cy, r)
                               : circlePtsWavy(cx, cy, r, Math.max(8, p.N), 0.05 + wave));
    }
  }
  return strokes;
}

function generateGlyph(type, V, seed, complexity = 0.7) {
  const rng = mulberry32(seed);
  const cx = 300, cy = 300;
  const spec = FAMILY[type] || FAMILY.INFP;
  // E는 I와 같은 나선 motif를 그대로 쓰되, 몰입도·사교성을 I/E 각자의 하위 구간으로
  // 선형 매핑해서 같은 슬라이더 값에서도 I/E 크기·감김이 뚜렷이 달라 보이게 한다.
  // (예전엔 값에 ±50 더하고 clamp했는데, 슬라이더 절반 구간이 0/100에 붙어버려
  // 그 구간에서는 움직여도 그림이 안 바뀌는 "죽은 구간"이 생겼다 → clamp 대신
  // 0~100 입력 전체를 하위 구간에 그대로 늘려 매핑해서 전 구간에서 항상 반응하게 함.)
  // I: 몰입도 50~100 / 사교성 0~50(더 작고 촘촘) · E: 몰입도 0~50 / 사교성 50~100(더 크고 성글게)
  const remap = (v, lo, hi) => lo + (v / 100) * (hi - lo);
  const isE = type[0] === "E";
  const V2 = isE
    ? { ...V, focus: remap(V.focus, 0, 50), sociability: remap(V.sociability, 50, 100) }
    : { ...V, focus: remap(V.focus, 50, 100), sociability: remap(V.sociability, 0, 50) };
  const rhythm = RHYTHM[temperamentOf(type)];
  const flavor = typeFlavor(type);
  const style = letterStyle(type);
  const p = mapVectors(V2, "spiral", flavor, complexity);
  p.wave = map(V.sensitivity, 0, 100, 0, style.waveSpan);
  return spiralGlyph(spec.motif, p, rhythm, style, flavor, rng, cx, cy);
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
html,body{margin:0;min-height:100%;}
.ps-root{--bg:#0d1017;--panel:#141a22;--ink:#ece4d3;--muted:#8b93a3;--brass:#c9a24b;--line:rgba(236,228,211,.12);
  min-height:100vh;background:radial-gradient(120% 80% at 50% -10%,#151d29 0%,var(--bg) 60%);
  color:var(--ink);font-family:'Noto Sans KR',sans-serif;-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;justify-content:center;position:relative;}
.ps-bg-pattern{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;}
.ps-bg-glyph{position:absolute;left:0;will-change:transform;
  animation-name:ps-bg-drift;animation-timing-function:linear;animation-iteration-count:infinite;}
.ps-bg-glyph svg path{stroke:var(--brass);fill:none;}
@keyframes ps-bg-drift{from{transform:translateX(-30vw);}to{transform:translateX(130vw);}}
@media (prefers-reduced-motion:reduce){.ps-bg-glyph{animation:none;left:-9999px;}}
.ps-wrap{max-width:820px;margin:0 auto;padding:40px 22px 64px;position:relative;z-index:1;width:100%;}
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

// 배경 장식: 실제 16종 문양 생성기(generateGlyph)로 후보 몇 개를 뽑아 반투명·다양한 크기로
// 왼쪽→오른쪽으로 천천히 흘러가게 한다(기계적인 반복 타일 대신 이 앱 고유의 유기적인 결).
// useMemo로 한 번만 계산(고정 seed) — 리렌더될 때마다 문양이 바뀌면 산만해짐.
const BG_TYPES = ["INTJ", "ISTJ", "ISFJ", "INFJ", "ISFP", "INFP", "ISTP", "INTP"];
function BgGlyphs() {
  const items = useMemo(() => {
    const rng = mulberry32(20260726);
    const V = { creativity: 55, focus: 55, sociability: 55, sensitivity: 55 };
    const n = 6;
    const out = [];
    for (let i = 0; i < n; i++) {
      const type = BG_TYPES[Math.floor(rng() * BG_TYPES.length)];
      const seed = Math.floor(rng() * 1e9);
      const strokes = generateGlyph(type, V, seed, 0.7);
      const size = Math.round(120 + rng() * 300);       // 다양한 크기
      const top = rng() * 88;                            // 세로 위치 %
      const duration = 55 + rng() * 55;                  // 55~110초(느리게 흐름)
      const delay = -rng() * duration;                   // 시작부터 제각각 위치에 있도록
      const opacity = 0.11 + rng() * 0.08;                // 반투명(11~19%, 평균 ~15%)
      out.push({ key: i, strokes, size, top, duration, delay, opacity });
    }
    return out;
  }, []);

  return (
    <div className="ps-bg-pattern">
      {items.map((it) => (
        <div key={it.key} className="ps-bg-glyph"
          style={{ top: `${it.top}%`, opacity: it.opacity,
                   animationDuration: `${it.duration}s`, animationDelay: `${it.delay}s` }}>
          <svg width={it.size} height={it.size} viewBox="0 0 600 600">
            {it.strokes.map((s, i) => (
              <path key={i} d={toPathD(s)} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            ))}
          </svg>
        </div>
      ))}
    </div>
  );
}

export default function PersonalitySignature() {
  const [screen, setScreen] = useState("intro"); // intro | quiz | result
  const [answers, setAnswers] = useState(Array(QUESTIONS.length).fill(null));
  const [qi, setQi] = useState(0);
  const [complexity, setComplexity] = useState(0.7); // 문양 복잡도(화려함 ↔ 그리는 시간)
  const [robotJob, setRobotJob] = useState(null); // { id, state, log_tail } | null — 로봇 드로잉 진행상태

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

  // 로봇으로 그리기: 로컬 브릿지 서버(gui_bridge_server.py, 기본 :8787)에
  // pen_up → 아크릴 드로잉 → pen_down → brush → grab 시퀀스 실행을 요청한다.
  // 브릿지 서버가 안 떠있으면 fetch 자체가 실패하므로 그 경우를 안내 메시지로 구분.
  const ROBOT_BRIDGE_URL = "http://localhost:8787";
  const sendDrawRequest = async (endpoint, bodyJson) => {
    setRobotJob({ id: null, state: "starting", log_tail: "" });
    try {
      const res = await fetch(`${ROBOT_BRIDGE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: bodyJson,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setRobotJob({ id: null, state: "error", log_tail: err.error || `HTTP ${res.status}` });
        return;
      }
      const { job_id } = await res.json();
      setRobotJob({ id: job_id, state: "queued", log_tail: "" });
      const poll = async () => {
        try {
          const r = await fetch(`${ROBOT_BRIDGE_URL}/status?job=${job_id}`);
          const j = await r.json();
          setRobotJob({ id: job_id, state: j.state, log_tail: j.log_tail || "", progress: j.progress || null });
          if (j.state === "queued" || j.state === "running") setTimeout(poll, 2000);
        } catch (e) {
          setRobotJob({ id: job_id, state: "error", log_tail: String(e) });
        }
      };
      setTimeout(poll, 1000);
    } catch (e) {
      setRobotJob({
        id: null, state: "error",
        log_tail: `브릿지 서버 연결 실패: ${e}. gui_bridge_server.py 가 켜져 있는지 확인하세요.`,
      });
    }
  };
  const drawOnRobot = () =>
    sendDrawRequest("/draw-signature",
      toRobotJSON(strokes, { type: result.type, vector: result.vector, axes: result.axes }));

  // 샘플 그리기(테스트용): 설문 없이 samples/ 의 기존 SVG를 서버에서 바로 그린다
  // (브릿지 서버가 파일을 변환 없이 그대로 사용 — square.svg, hex_spiral.svg).
  const drawSample = (name) =>
    sendDrawRequest("/draw-sample", JSON.stringify({ sample: name }));

  const robotBusy = robotJob && ["starting", "queued", "running"].includes(robotJob.state);

  // 긴급 중지: 로봇에 정지 명령부터 보내고, 진행 중이던 시퀀스 프로세스도 종료한다.
  // 상태를 알 수 없어도(robotJob이 null이어도) 언제든 누를 수 있게 항상 활성화.
  const [estopBusy, setEstopBusy] = useState(false);
  const estopRobot = async () => {
    setEstopBusy(true);
    try {
      const res = await fetch(`${ROBOT_BRIDGE_URL}/estop`, { method: "POST" });
      const j = await res.json();
      setRobotJob({
        id: robotJob?.id ?? null, state: "stopped",
        log_tail: j.stop_message || (j.stop_sent ? "정지 명령 전송됨" : "정지 명령 실패"),
      });
    } catch (e) {
      setRobotJob({ id: null, state: "error", log_tail: `긴급중지 요청 실패: ${e}` });
    } finally {
      setEstopBusy(false);
    }
  };

  // 원위치: 준비자세(0,0,90,0,90,0)로 복귀. 다른 작업이 실행 중이면 서버가 거절한다.
  const [homeBusy, setHomeBusy] = useState(false);
  const [homeMsg, setHomeMsg] = useState(null);
  const goHomeRobot = async () => {
    setHomeBusy(true);
    setHomeMsg(null);
    try {
      const res = await fetch(`${ROBOT_BRIDGE_URL}/go-home`, { method: "POST" });
      const j = await res.json();
      setHomeMsg(j.ok ? "원위치 완료" : `원위치 실패: ${j.message}`);
    } catch (e) {
      setHomeMsg(`원위치 요청 실패: ${e}`);
    } finally {
      setHomeBusy(false);
    }
  };

  // 펜 내려놓기: pen_down 모션 실행. 원위치와 같은 방식(작업 중이면 서버가 409로 거절).
  const [penDownBusy, setPenDownBusy] = useState(false);
  const penDownRobot = async () => {
    setPenDownBusy(true);
    setHomeMsg(null);
    try {
      const res = await fetch(`${ROBOT_BRIDGE_URL}/pen-down`, { method: "POST" });
      const j = await res.json();
      setHomeMsg(j.ok ? "펜 내려놓기 완료" : `펜 내려놓기 실패: ${j.message}`);
    } catch (e) {
      setHomeMsg(`펜 내려놓기 요청 실패: ${e}`);
    } finally {
      setPenDownBusy(false);
    }
  };

  // 엔드이펙터(TCP) 오프셋 길이 실시간 표시 — 이름 대신 '길이(mm)'로 보여줘서, 컨트롤러가
  // TCP를 조용히 리셋(pen 289mm → 플랜지 0mm)한 걸 한눈에 감지한다. 그리는 중엔 조회를
  // 쉬어 ROS 노드 churn을 피한다. 약 10초마다 폴링.
  const [tcpInfo, setTcpInfo] = useState(null);
  const EXPECTED_TCP_LEN = 289;   // pen 오프셋 길이(mm)
  useEffect(() => {
    let alive = true;
    const fetchTcp = async () => {
      if (robotBusy) return;
      try {
        const r = await fetch(`${ROBOT_BRIDGE_URL}/tcp-info`);
        const j = await r.json();
        if (alive) setTcpInfo(j);
      } catch (e) {
        if (alive) setTcpInfo({ ok: false, error: "브릿지 연결 안 됨" });
      }
    };
    fetchTcp();
    const id = setInterval(fetchTcp, 10000);
    return () => { alive = false; clearInterval(id); };
  }, [robotBusy]);

  const renderTcpBadge = () => {
    if (!tcpInfo) return null;
    if (!tcpInfo.ok) {
      return (
        <p className="ps-muted" style={{ fontSize: 12, textAlign: "center", marginBottom: 10 }}>
          엔드이펙터: 조회 불가 ({tcpInfo.error || "알 수 없음"})
        </p>
      );
    }
    const len = tcpInfo.len_mm;
    const isPen = Math.abs(len - EXPECTED_TCP_LEN) <= 12;
    return (
      <p style={{
        fontSize: 12.5, textAlign: "center", marginBottom: 10, fontWeight: 600,
        color: isPen ? "#5aa469" : "#e0663f",
      }}>
        엔드이펙터 오프셋 <span className="ps-mono">{len}mm</span>{" "}
        {isPen ? "✓ pen 정상" : `⚠ pen 아님·리셋 의심 (정상 ~${EXPECTED_TCP_LEN}mm)`}
      </p>
    );
  };

  return (
    <div className="ps-root">
      <style>{CSS}</style>
      <BgGlyphs />
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

            {/* 테스트용: 설문 없이 기존 샘플 SVG로 로봇 파이프라인만 빠르게 확인 */}
            <div style={{ marginTop: 28, paddingTop: 22, borderTop: "1px solid var(--line)" }}>
              {renderTcpBadge()}
              {/* 로봇 안전 제어 — 테스트 중 언제든(작업 상태 무관) 누를 수 있게 항상 활성화 */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center", marginBottom: 14 }}>
                <button
                  onClick={estopRobot}
                  disabled={estopBusy}
                  style={{
                    border: "1px solid #c94b3a", background: estopBusy ? "#7a2e24" : "#c94b3a",
                    color: "#fff", padding: "12px 22px", borderRadius: 2, fontSize: 14,
                    fontWeight: 700, cursor: estopBusy ? "default" : "pointer", letterSpacing: ".04em",
                    fontFamily: "inherit",
                  }}
                >
                  {estopBusy ? "정지 명령 전송 중…" : "⏹ 긴급 중지"}
                </button>
                <button className="ps-btn" onClick={goHomeRobot} disabled={homeBusy}>
                  {homeBusy ? "원위치 이동 중…" : "원위치"}
                </button>
                <button className="ps-btn" onClick={penDownRobot} disabled={penDownBusy}>
                  {penDownBusy ? "펜 내려놓는 중…" : "펜 내려놓기"}
                </button>
              </div>
              {homeMsg && (
                <p className="ps-muted" style={{ textAlign: "center", fontSize: 12, marginBottom: 10 }}>
                  {homeMsg}
                </p>
              )}

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
                <button className="ps-btn" onClick={() => drawSample("square")} disabled={robotBusy}>
                  {robotBusy ? "로봇 작업 중…" : "샘플: 사각형"}
                </button>
                <button className="ps-btn" onClick={() => drawSample("hex_spiral")} disabled={robotBusy}>
                  {robotBusy ? "로봇 작업 중…" : "샘플: hex_spiral"}
                </button>
              </div>
              <p className="ps-muted" style={{ fontSize: 11, marginTop: 8 }}>
                samples/의 기존 SVG로 pen_up→그리기→pen_down→brush→grab 전체를 바로 테스트합니다
              </p>
              {robotJob && (
                <p className="ps-muted" style={{ fontSize: 12, marginTop: 6 }}>
                  {robotJob.state === "starting" && "브릿지 서버에 연결하는 중…"}
                  {robotJob.state === "queued" && "대기열에 등록됨…"}
                  {robotJob.state === "running" &&
                    (robotJob.progress
                      ? `그리는 중… ${robotJob.progress.current}/${robotJob.progress.total}획 (${robotJob.progress.percent}%)`
                      : "pen_up → 드로잉 → pen_down → brush → grab 진행 중…")}
                  {robotJob.state === "done" && "완료! 확인해 보세요."}
                  {robotJob.state === "error" && (
                    (robotJob.log_tail || "").includes("아크릴판이 감지되지")
                      ? "⚠ 아크릴판이 감지되지 않았습니다. 원위치로 복귀했어요. 판을 제자리에 놓고 다시 눌러주세요."
                      : `실패: ${robotJob.log_tail || "알 수 없는 오류"}`)}
                  {robotJob.state === "stopped" && `긴급중지됨: ${robotJob.log_tail || ""}`}
                </p>
              )}
              {robotJob && robotJob.state === "running" && robotJob.progress && (
                <div className="ps-bar-track" style={{ marginTop: 6 }}>
                  <div className="ps-bar-fill" style={{ width: `${robotJob.progress.percent}%` }} />
                </div>
              )}
            </div>
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
                <Bar label="몰입도" value={result.vector.focus} />
                <Bar label="사교성" value={result.vector.sociability} />
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
                  MBTI 유형 → 기본 도형 · 창의성 → 대칭 차수·퍼짐 · 몰입도 → 겹 수·나선 정갈함 · 사교성 → 크기 · 감수성 → 물결 변조
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

            {/* 로봇 안전 제어 — 언제든(작업 상태 무관) 누를 수 있게 항상 활성화 */}
            {renderTcpBadge()}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center", marginBottom: 10 }}>
              <button
                onClick={estopRobot}
                disabled={estopBusy}
                style={{
                  border: "1px solid #c94b3a", background: estopBusy ? "#7a2e24" : "#c94b3a",
                  color: "#fff", padding: "12px 22px", borderRadius: 2, fontSize: 14,
                  fontWeight: 700, cursor: estopBusy ? "default" : "pointer", letterSpacing: ".04em",
                  fontFamily: "inherit",
                }}
              >
                {estopBusy ? "정지 명령 전송 중…" : "⏹ 긴급 중지"}
              </button>
              <button className="ps-btn" onClick={goHomeRobot} disabled={homeBusy}>
                {homeBusy ? "원위치 이동 중…" : "원위치"}
              </button>
              <button className="ps-btn" onClick={penDownRobot} disabled={penDownBusy}>
                {penDownBusy ? "펜 내려놓는 중…" : "펜 내려놓기"}
              </button>
            </div>
            {homeMsg && (
              <p className="ps-muted" style={{ textAlign: "center", fontSize: 12, marginBottom: 10 }}>
                {homeMsg}
              </p>
            )}

            {/* 내보내기 */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
              <button className="ps-btn ps-primary" onClick={drawOnRobot} disabled={robotBusy}>
                {robotBusy ? "로봇 작업 중…" : "로봇으로 그리기"}
              </button>
              <button className="ps-btn" onClick={() => download(`signature_${result.type}.svg`, toSVG(strokes, { type: result.type }), "image/svg+xml")}>
                SVG 내려받기
              </button>
              <button className="ps-btn" onClick={() => download(`signature_${result.type}.json`, toRobotJSON(strokes, { type: result.type, vector: result.vector, axes: result.axes }), "application/json")}>
                로봇용 폴리라인(JSON)
              </button>
              <button className="ps-btn" onClick={restart}>다시 하기</button>
            </div>
            {robotJob && (
              <p className="ps-muted" style={{ textAlign: "center", fontSize: 12, marginTop: 14 }}>
                {robotJob.state === "starting" && "브릿지 서버에 연결하는 중…"}
                {robotJob.state === "queued" && "대기열에 등록됨…"}
                {robotJob.state === "running" &&
                  (robotJob.progress
                    ? `그리는 중… ${robotJob.progress.current}/${robotJob.progress.total}획 (${robotJob.progress.percent}%)`
                    : "pen_up → 드로잉 → pen_down → brush → grab 진행 중…")}
                {robotJob.state === "done" && "완료! 완성된 아크릴판을 확인하세요."}
                {robotJob.state === "error" && (
                  (robotJob.log_tail || "").includes("아크릴판이 감지되지")
                    ? "⚠ 아크릴판이 감지되지 않았습니다. 원위치로 복귀했어요. 판을 제자리에 놓고 [로봇으로 그리기]를 다시 눌러주세요."
                    : `실패: ${robotJob.log_tail || "알 수 없는 오류"}`)}
                {robotJob.state === "stopped" && `긴급중지됨: ${robotJob.log_tail || ""}`}
              </p>
            )}
            {robotJob && robotJob.state === "running" && robotJob.progress && (
              <div className="ps-bar-track" style={{ maxWidth: 300, margin: "6px auto 0" }}>
                <div className="ps-bar-fill" style={{ width: `${robotJob.progress.percent}%` }} />
              </div>
            )}
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
