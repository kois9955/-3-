import calendar
import datetime
import holidays
from ortools.sat.python import cp_model
import pandas as pd
import streamlit as st

st.set_page_config(page_title="간호사 근무표 자동 생성기", layout="wide")

st.title("🏥 간호사 근무표 자동 생성기")

st.divider()

# ---------------------------------------------------------
# 1. 기본 설정 (연도, 월, 휴무일, 간호사 인원 설정)
# ---------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    year = st.number_input(
        "연도 (YEAR)", min_value=2024, max_value=2030, value=2026
    )
with col2:
    month = st.number_input("월 (MONTH)", min_value=1, max_value=12, value=8)
with col3:
    target_off = st.number_input(
        "목표 오프(off) 개수",
        min_value=1,
        max_value=15,
        value=8,
        help="간호사당 목표 휴무일 수 (최우선 반영하되, 불가피할 경우 -OFF 가능)",
    )
with col4:
    num_nurses = st.number_input(
        "총 간호사 수 (기본: 5명)",
        min_value=3,
        max_value=15,
        value=5,
        step=1,
        help="기본 5명 세팅 (최소 3명 이상 조정 가능)",
    )

# 한국 법정 공휴일/대체공휴일 자동 추출
kr_holidays = holidays.KR(years=year)
auto_holidays = set()
for date_obj, name in kr_holidays.items():
    if date_obj.month == month and date_obj.weekday() < 5:  # 월~금 평일 공휴일만
        auto_holidays.add(date_obj.day)

col_h1, col_h2 = st.columns([2, 1])
with col_h1:
    custom_holidays_input = st.text_input(
        "빨간날(대체공휴일, 공휴일 등) 날짜 추가 입력",
        value="",
        help="쉼표로 구분하여 입력 (예: 15, 20)",
    )

try:
    custom_holidays = set(
        int(x.strip())
        for x in custom_holidays_input.split(",")
        if x.strip().isdigit()
    )
except:
    custom_holidays = set()

all_holidays = auto_holidays.union(custom_holidays)

if auto_holidays:
    auto_days_str = ", ".join(f"{d}일" for d in sorted(auto_holidays))
    st.info(f"💡 **자동 감지된 평일 공휴일/대체공휴일**: {auto_days_str}")
else:
    st.caption("💡 이번 달 평일 공휴일/대체공휴일이 없습니다.")

num_days = calendar.monthrange(year, month)[1]

# ---------------------------------------------------------
# 간호사 동적 생성 및 이름 지정
# ---------------------------------------------------------
st.markdown("##### 👥 간호사 이름 설정")
default_names = ["수간호사"] + [
    f"간호사 {chr(65+i)}" for i in range(num_nurses - 1)
]  # A, B, C, D...

NURSES = [f"N_{i}" for i in range(num_nurses)]
DISPLAY_NAME = {}

cols_name = st.columns(min(num_nurses, 6))
for i in range(num_nurses):
    col_idx = i % 6
    with cols_name[col_idx]:
        DISPLAY_NAME[NURSES[i]] = st.text_input(
            f"간호사 {i+1}", value=default_names[i], key=f"nurse_name_{i}"
        )

# 자동 생성시 기본 사용되는 듀티
SHIFT_OPTS = ["off", "D", "E", "N"]
# 수정 및 수동입력용 확장 듀티 항목
EDIT_SHIFT_OPTS = ["off", "D", "E", "N", "DE", "D2", "N2"]

st.divider()

# ---------------------------------------------------------
# 2. 전 달 마지막 3일간 근무 입력
# ---------------------------------------------------------
prev_month = 12 if month == 1 else month - 1
st.subheader(f"📅 전달({prev_month}월) 마지막 3일간 근무 입력")

prev_schedule = {}
cols_prev = st.columns(min(num_nurses, 5))

for idx, n in enumerate(NURSES):
    col_target = cols_prev[idx % 5]
    with col_target:
        st.markdown(f"**{DISPLAY_NAME[n]}**")
        p29 = st.selectbox(
            "전달 -2일", SHIFT_OPTS, index=0, key=f"p29_{n}"
        )
        p30 = st.selectbox(
            "전달 -1일", SHIFT_OPTS, index=0, key=f"p30_{n}"
        )
        p31 = st.selectbox(
            "전달 마지막날", SHIFT_OPTS, index=0, key=f"p31_{n}"
        )
        prev_schedule[n] = [p29, p30, p31]

st.divider()

# ---------------------------------------------------------
# 3. 간호사별 듀티/오프 신청
# ---------------------------------------------------------
st.subheader("📌 간호사별 듀티/오프 신청")

if "req_shifts_store" not in st.session_state:
    st.session_state.req_shifts_store = {n: {} for n in NURSES}

tabs = st.tabs([DISPLAY_NAME[n] for n in NURSES])

for idx, n in enumerate(NURSES):
    if n not in st.session_state.req_shifts_store:
        st.session_state.req_shifts_store[n] = {}

    with tabs[idx]:
        st.write(f"**{DISPLAY_NAME[n]} 신청 현황**")

        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            sel_day = st.number_input(
                "날짜 선택",
                min_value=1,
                max_value=num_days,
                value=1,
                key=f"day_sel_{n}",
            )
        with c2:
            sel_shift = st.selectbox(
                "원하는 듀티", SHIFT_OPTS, index=0, key=f"shift_sel_{n}"
            )
        with c3:
            st.write("")
            st.write("")
            if st.button("➕ 신청 추가/수정", key=f"add_btn_{n}"):
                st.session_state.req_shifts_store[n][sel_day] = sel_shift
                st.toast(
                    f"{DISPLAY_NAME[n]}: {sel_day}일 [{sel_shift}] 신청 완료!"
                )

        if st.session_state.req_shifts_store[n]:
            st.markdown("---")
            st.write("📋 **현재 신청된 내역:**")
            sorted_reqs = sorted(
                st.session_state.req_shifts_store[n].items()
            )
            req_text = " | ".join(
                [f"**{d}일**: {s}" for d, s in sorted_reqs]
            )
            st.info(req_text)

            if st.button("🗑️ 이 간호사의 신청 초기화", key=f"clear_btn_{n}"):
                st.session_state.req_shifts_store[n] = {}
                st.rerun()

requested_shifts = st.session_state.req_shifts_store

st.divider()


# ---------------------------------------------------------
# 4. CP-SAT 근무표 생성 함수
# ---------------------------------------------------------
def generate_schedule(
    YEAR, MONTH, HOLIDAYS, PREV_SCHED, REQ_SHIFTS, TARGET_OFF
):
    OFF, DAY, EVE, NGT = 0, 1, 2, 3
    SHIFT_LABEL = {OFF: "off", DAY: "D", EVE: "E", NGT: "N"}
    LABEL_TO_INT = {"off": OFF, "D": DAY, "E": EVE, "N": NGT}

    num_days = calendar.monthrange(YEAR, MONTH)[1]
    DAYS = list(range(1, num_days + 1))
    weekday_of = {
        d: datetime.date(YEAR, MONTH, d).weekday() for d in DAYS
    }

    def is_special_day(d):
        return weekday_of[d] in (5, 6) or d in HOLIDAYS

    model = cp_model.CpModel()
    HN_KEY = NURSES[0]  # 첫 번째 간호사를 수간호사로 지정
    JUNIORS = [n for n in NURSES if n != HN_KEY]

    shift, is_off, is_D, is_E, is_N = {}, {}, {}, {}, {}

    for n in NURSES:
        for d in DAYS:
            shift[n, d] = model.NewIntVar(0, 3, f"shift_{n}_{d}")
            is_off[n, d] = model.NewBoolVar(f"off_{n}_{d}")
            is_D[n, d] = model.NewBoolVar(f"D_{n}_{d}")
            is_E[n, d] = model.NewBoolVar(f"E_{n}_{d}")
            is_N[n, d] = model.NewBoolVar(f"N_{n}_{d}")
            model.Add(shift[n, d] == OFF).OnlyEnforceIf(is_off[n, d])
            model.Add(shift[n, d] != OFF).OnlyEnforceIf(is_off[n, d].Not())
            model.Add(shift[n, d] == DAY).OnlyEnforceIf(is_D[n, d])
            model.Add(shift[n, d] != DAY).OnlyEnforceIf(is_D[n, d].Not())
            model.Add(shift[n, d] == EVE).OnlyEnforceIf(is_E[n, d])
            model.Add(shift[n, d] != EVE).OnlyEnforceIf(is_E[n, d].Not())
            model.Add(shift[n, d] == NGT).OnlyEnforceIf(is_N[n, d])
            model.Add(shift[n, d] != NGT).OnlyEnforceIf(is_N[n, d].Not())

    # 개인별 신청 듀티 반영
    for n in NURSES:
        for req_d, req_s in REQ_SHIFTS.get(n, {}).items():
            target_val = LABEL_TO_INT[req_s]
            model.Add(shift[n, req_d] == target_val)

            if req_s == "off":
                if req_d > 1:
                    model.Add(is_N[n, req_d - 1] == 0)

    # 전 달 말일 연계
    for n in JUNIORS:
        p29, p30, p31 = [LABEL_TO_INT[x] for x in PREV_SCHED[n]]

        if p31 == NGT:
            model.AddBoolOr([is_N[n, 1], is_off[n, 1]])

        prev_work_count = sum(1 for x in [p29, p30, p31] if x != OFF)
        if prev_work_count > 0:
            max_allowed_first_days = 6 - prev_work_count
            if max_allowed_first_days < 1:
                model.Add(is_off[n, 1] == 1)
            else:
                model.Add(
                    sum(
                        is_off[n, d]
                        for d in range(1, max_allowed_first_days + 1)
                    )
                    >= 1
                )

    # 수간호사 고정 규칙
    for d in DAYS:
        model.Add(is_E[HN_KEY, d] == 0)
        model.Add(is_N[HN_KEY, d] == 0)

        if d not in REQ_SHIFTS.get(HN_KEY, {}):
            if is_special_day(d):
                model.Add(is_off[HN_KEY, d] == 1)
            else:
                model.Add(is_D[HN_KEY, d] == 1)

    penalty_terms = []

    # 근무 인력 고정 조건 (N 1명 고정, E 1명 고정, 주말/공휴일 D 1명 고정)
    for d in DAYS:
        d_count = sum(is_D[n, d] for n in NURSES)
        e_count = sum(is_E[n, d] for n in NURSES)
        n_count = sum(is_N[n, d] for n in NURSES)

        # 절대 규칙: E와 N은 무조건 하루에 딱 1명씩만 배치
        model.Add(e_count == 1)
        model.Add(n_count == 1)

        if is_special_day(d):
            # 주말/공휴일 데이(D)는 무조건 1명 고정
            model.Add(d_count == 1)
        else:
            # 평일 데이(D): 최소 1명 이상은 필수
            model.Add(d_count >= 1)
            # 2순위: 평일 데이(D) 2명 선호 (1명일 경우 소량의 벌점 부여)
            is_d_less_than_2 = model.NewBoolVar(f"d_less_2_{d}")
            model.Add(d_count < 2).OnlyEnforceIf(is_d_less_than_2)
            model.Add(d_count >= 2).OnlyEnforceIf(is_d_less_than_2.Not())
            penalty_terms.append(is_d_less_than_2 * 50)

    # 나이트 연속 3일 제한 및 N 다음 D/E 금지
    for n in JUNIORS:
        for s in range(1, num_days - 2):
            window = range(s, s + 4)
            model.Add(sum(is_N[n, d] for d in window) <= 3)
        for d in DAYS[:-1]:
            model.AddBoolOr(
                [is_N[n, d].Not(), is_N[n, d + 1], is_off[n, d + 1]]
            )

    # 연속 근무 제한 (최대 6일)
    for n in NURSES:
        for s in range(1, num_days - 5):
            window = range(s, s + 7)
            model.Add(sum(is_off[n, d] for d in window) >= 1)

    # 총량 변수
    off_total = {}
    d_total = {}
    e_total = {}
    n_total = {}
    for n in JUNIORS:
        off_total[n] = sum(is_off[n, d] for d in DAYS)
        d_total[n] = sum(is_D[n, d] for d in DAYS)
        e_total[n] = sum(is_E[n, d] for d in DAYS)
        n_total[n] = sum(is_N[n, d] for d in DAYS)

    # 1순위: 오프(off) 개수 맞추기 (최우선하되, 불가능할 경우 -OFF 허용)
    for n in JUNIORS:
        off_diff = model.NewIntVar(-31, 31, f"off_diff_{n}")
        model.Add(off_diff == off_total[n] - TARGET_OFF)
        abs_off_diff = model.NewIntVar(0, 31, f"abs_off_diff_{n}")
        model.AddAbsEquality(abs_off_diff, off_diff)
        # 오프 개수가 모자라거나 넘칠수록 점수 감점 (우선순위 1위)
        penalty_terms.append(abs_off_diff * 1500)

    # E->D 역교대 방지
    for n in JUNIORS:
        for d in DAYS[:-1]:
            bad = model.NewBoolVar(f"ED_{n}_{d}")
            model.AddBoolAnd([is_E[n, d], is_D[n, d + 1]]).OnlyEnforceIf(bad)
            model.AddBoolOr(
                [is_E[n, d].Not(), is_D[n, d + 1].Not()]
            ).OnlyEnforceIf(bad.Not())
            penalty_terms.append(bad * 1000)

    # 퐁당퐁당 패턴 방지
    for n in JUNIORS:
        for d in range(2, num_days):
            single_off = model.NewBoolVar(f"soff_{n}_{d}")
            model.AddBoolAnd(
                [is_off[n, d - 1].Not(), is_off[n, d], is_off[n, d + 1].Not()]
            ).OnlyEnforceIf(single_off)
            model.AddBoolOr(
                [is_off[n, d - 1], is_off[n, d].Not(), is_off[n, d + 1]]
            ).OnlyEnforceIf(single_off.Not())
            penalty_terms.append(single_off * 300)

            single_work = model.NewBoolVar(f"swork_{n}_{d}")
            model.AddBoolAnd(
                [is_off[n, d - 1], is_off[n, d].Not(), is_off[n, d + 1]]
            ).OnlyEnforceIf(single_work)
            model.AddBoolOr(
                [is_off[n, d - 1].Not(), is_off[n, d], is_off[n, d + 1].Not()]
            ).OnlyEnforceIf(single_work.Not())
            penalty_terms.append(single_work * 300)

    # 간호사 간 각 듀티 개수 균등 배분
    for i in range(len(JUNIORS)):
        for j in range(i + 1, len(JUNIORS)):
            n1, n2 = JUNIORS[i], JUNIORS[j]

            odiff = model.NewIntVar(-31, 31, f"odiff_{n1}_{n2}")
            model.Add(odiff == off_total[n1] - off_total[n2])
            abs_odiff = model.NewIntVar(0, 31, f"abs_odiff_{n1}_{n2}")
            model.AddAbsEquality(abs_odiff, odiff)
            penalty_terms.append(abs_odiff * 300)

            for shift_tot, label in [
                (d_total, "d"),
                (e_total, "e"),
                (n_total, "n"),
            ]:
                sdiff = model.NewIntVar(-31, 31, f"{label}diff_{n1}_{n2}")
                model.Add(sdiff == shift_tot[n1] - shift_tot[n2])
                abs_sdiff = model.NewIntVar(0, 31, f"abs_{label}diff_{n1}_{n2}")
                model.AddAbsEquality(abs_sdiff, sdiff)
                penalty_terms.append(abs_sdiff * 200)

    model.Minimize(sum(penalty_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        wk_kr = ["월", "화", "수", "목", "금", "토", "일"]
        cols = [
            f"{d}({wk_kr[datetime.date(YEAR, MONTH, d).weekday()][0]})"
            for d in DAYS
        ]

        data = []
        for n in NURSES:
            row = [SHIFT_LABEL[solver.Value(shift[n, d])] for d in DAYS]
            data.append([DISPLAY_NAME[n]] + row)

        return pd.DataFrame(data, columns=["구분"] + cols)
    else:
        return None


# ---------------------------------------------------------
# 5. 실행 및 결과 출력
# ---------------------------------------------------------
if st.button("🚀 맞춤 근무표 생성하기", type="primary"):
    with st.spinner("근무표 계산 중..."):
        df_result = generate_schedule(
            year,
            month,
            all_holidays,
            prev_schedule,
            requested_shifts,
            target_off,
        )

    if df_result is not None:
        st.session_state.current_schedule_df = df_result
        st.success(f"✨ {year}년 {month}월 근무표가 완성되었습니다!")
    else:
        st.error(
            "❌ 입력하신 조건(신청 듀티, 연속 근무 제약 등)이 수급 조건과 완전히 충돌하여 근무표 생성이 불가능합니다. 신청 듀티를 조금 조율해 주세요."
        )

if "current_schedule_df" in st.session_state:
    st.markdown("---")
    st.subheader("📋 근무표 수정 및 확인")
    st.caption(
        "💡 **[위쪽 입력창]**에서 듀티를 직접 수정하시면, **[아래쪽 표]에서 연한 빨강 형광펜과 D/E/N/off 합계가 즉시 실시간 업데이트**됩니다."
    )

    df_current = st.session_state.current_schedule_df
    date_cols = [
        c
        for c in df_current.columns
        if c not in ["구분", "D", "E", "N", "off"]
    ]

    # 날짜 컬럼 드롭다운 수정 설정
    column_config = {
        "구분": st.column_config.TextColumn("구분", disabled=True)
    }
    for col in date_cols:
        column_config[col] = st.column_config.SelectboxColumn(
            col, options=EDIT_SHIFT_OPTS, required=True
        )

    raw_date_df = df_current[["구분"] + date_cols]

    # 1. 듀티 수정용 에디터
    edited_date_df = st.data_editor(
        raw_date_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        key="schedule_editor",
    )


    # D, E, N, off 합계 실시간 계산 함수
    def calc_totals(row):
        vals = list(row[date_cols])
        return pd.Series(
            [
                vals.count("D"),
                vals.count("E"),
                vals.count("N"),
                vals.count("off"),
            ]
        )


    totals_df = edited_date_df.apply(calc_totals, axis=1)
    totals_df.columns = ["D", "E", "N", "off"]

    # 수정된 데이터 + 실시간 합계 결합
    final_df = pd.concat([edited_date_df, totals_df], axis=1)


    # off 셀 연한 빨강 형광펜 서식 함수
    def style_off(val):
        if str(val).strip().lower() == "off":
            return "background-color: #FFD2D2; color: #D8000C; font-weight: bold;"
        return ""


    styled_final_df = final_df.style.map(style_off)

    # 2. 형광펜 및 실시간 합계가 포함된 최종 렌더링 표
    st.dataframe(styled_final_df, use_container_width=True, hide_index=True)

    # 3. 엑셀 다운로드 버튼
    csv_data = final_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 최종 근무표 엑셀(CSV) 다운로드",
        data=csv_data,
        file_name=f"근무표_{year}년_{month}월.csv",
        mime="text/csv",
        type="primary",
    )