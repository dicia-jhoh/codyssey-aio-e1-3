"""Mini NPU Simulator — MAC 연산으로 Cross/X 패턴을 판정한다.

외부 라이브러리 없이 표준 라이브러리(json, time)만 쓴다.
실행: python main.py  → 모드 1(사용자 입력 3×3) 또는 모드 2(data.json 분석)
"""

import json
import math
import time

EPSILON = 1e-9  # 두 점수 차이가 이보다 작으면 동점(판정 불가)
EPSILON_TEXT = "1e-9"
REPEAT = 10  # 성능 측정 반복 횟수
DATA_PATH = "data.json"
BENCH_SIZES = [3, 5, 13, 25]

CROSS = "Cross"
X = "X"
UNDECIDED = "UNDECIDED"

# data.json 은 같은 뜻을 여러 표기로 쓴다 — 내부에서는 표준 라벨 두 개만 쓴다
LABEL_ALIASES = {
    "+": CROSS,
    "cross": CROSS,
    "x": X,
}

LINE = "#" + "-" * 39


# ---------------------------------------------------------------- 데이터 구조


def make_matrix(n, fill=0.0):
    """n×n 2차원 리스트를 만든다."""
    return [[fill for _ in range(n)] for _ in range(n)]


def get_value(matrix, row, col):
    return matrix[row][col]


def set_value(matrix, row, col, value):
    matrix[row][col] = value


def is_square(matrix, n):
    """matrix 가 n×n 숫자 2차원 리스트인지 확인한다."""
    if not isinstance(matrix, list) or len(matrix) != n:
        return False
    for row in matrix:
        if not isinstance(row, list) or len(row) != n:
            return False
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            # json 은 NaN·Infinity 를 읽어 들인다 — 비교가 정의되지 않아 거짓 PASS 를 낸다
            if isinstance(value, float) and not math.isfinite(value):
                return False
    return True


# ---------------------------------------------------------------- 연산


def mac(a, b):
    """같은 위치끼리 곱해서 모두 더한다(Multiply-Accumulate). 반복문으로 직접 계산."""
    total = 0.0
    for i in range(len(a)):
        row_a = a[i]
        row_b = b[i]
        for j in range(len(row_a)):
            total += row_a[j] * row_b[j]
    return total


def is_close(a, b, epsilon=EPSILON):
    """두 점수의 차이가 epsilon 보다 작으면 같은 값으로 본다."""
    return abs(a - b) < epsilon


def decide(score_a, score_b, label_a, label_b, epsilon=EPSILON):
    """점수가 큰 쪽의 라벨을 돌려준다. 차이가 epsilon 미만이거나 점수가 유한하지 않으면 UNDECIDED.

    아주 큰 값(1e308 등)은 곱하고 더하다 inf 로 넘쳐서 inf 끼리 비교하면 아무 쪽이나 고르게 된다.
    """
    if not (math.isfinite(score_a) and math.isfinite(score_b)):
        return UNDECIDED
    if is_close(score_a, score_b, epsilon):
        return UNDECIDED
    return label_a if score_a > score_b else label_b


def normalize_label(raw):
    """'+'·'cross'·'x' 같은 표기를 표준 라벨(Cross/X)로 바꾼다. 모르는 표기면 None."""
    if not isinstance(raw, str):
        return None
    return LABEL_ALIASES.get(raw.strip().lower())


def parse_size(text):
    """'13' → 13. 양의 정수가 아니면 None(isdigit 은 '²' 같은 문자도 통과시켜 int 에서 터진다)."""
    try:
        n = int(text)
    except ValueError:
        return None
    return n if n > 0 else None


def size_from_key(key):
    """'size_13_2' → 13. 형식이 다르면 None."""
    parts = key.split("_")
    if len(parts) != 3 or parts[0] != "size":
        return None
    try:
        index = int(parts[2])
    except ValueError:
        return None
    if index < 0:  # 순번은 0 이상 — 'size_5_-1' 같은 키는 형식 오류
        return None
    return parse_size(parts[1])


# ---------------------------------------------------------------- 패턴 생성기(보너스 2)


def generate_cross(n):
    """가운데 행·열이 1인 n×n 십자가 패턴."""
    middle = n // 2
    matrix = make_matrix(n)
    for i in range(n):
        set_value(matrix, middle, i, 1.0)
        set_value(matrix, i, middle, 1.0)
    return matrix


def generate_x(n):
    """두 대각선이 1인 n×n X 패턴."""
    matrix = make_matrix(n)
    for i in range(n):
        set_value(matrix, i, i, 1.0)
        set_value(matrix, i, n - 1 - i, 1.0)
    return matrix


GENERATORS = {"cross": generate_cross, "x": generate_x}


# ---------------------------------------------------------------- 성능 측정


def measure_mac_time(n, repeat=REPEAT):
    """n×n 패턴 두 개의 MAC 를 repeat 번 돌린 평균 시간(ms). 연산 구간만 잰다."""
    a = generate_cross(n)
    b = generate_x(n)
    start = time.perf_counter()
    for _ in range(repeat):
        mac(a, b)
    elapsed = time.perf_counter() - start
    return elapsed / repeat * 1000


def analyze_complexity(sizes, times):
    """크기가 커질 때 시간이 몇 배 늘었는지와, 같은 구간의 N² 배율을 나란히 낸다."""
    pairs = []
    time_ratios = []
    ops_ratios = []
    for i in range(len(sizes) - 1):
        pairs.append([sizes[i], sizes[i + 1]])
        time_ratios.append(times[i + 1] / times[i] if times[i] > 0 else 0.0)
        ops_ratios.append((sizes[i + 1] ** 2) / (sizes[i] ** 2))
    return {
        "size_pairs": pairs,
        "time_ratios": time_ratios,
        "ops_ratios": ops_ratios,
        "estimated_order": "O(N^2)",
    }


def print_benchmark(sizes, repeat=REPEAT):
    print(LINE)
    print(f"# [3] 성능 분석 (평균/{repeat}회)")
    print(LINE)
    print(f"{'크기':<10}{'평균 시간(ms)':>14}{'연산 횟수':>12}")
    print("-" * 37)
    times = []
    for n in sizes:
        ms = measure_mac_time(n, repeat)
        times.append(ms)
        print(f"{f'{n}×{n}':<10}{ms:>14.4f}{n * n:>12}")
    return times


# ---------------------------------------------------------------- 1차원 최적화(보너스 1)


def flatten(matrix):
    """n×n 2차원 리스트를 길이 n² 1차원 리스트로 편다."""
    flat = []
    n = len(matrix)
    for i in range(n):
        for j in range(len(matrix[i])):
            flat.append(get_value(matrix, i, j))
    return flat


def mac_flat(a, b):
    """1차원으로 편 두 배열의 MAC. 행을 따라가는 이중 인덱싱이 없다."""
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def compare_flat(sizes, repeat=REPEAT):
    """같은 입력·같은 반복 횟수로 2차원 MAC 와 1차원 MAC 의 평균 시간(ms)을 비교한다."""
    print(LINE)
    print(f"# [5] 보너스: 2차원 vs 1차원 MAC (평균/{repeat}회)")
    print(LINE)
    print(f"{'크기':<10}{'2차원(ms)':>12}{'1차원(ms)':>12}{'배율':>8}")
    rows = []
    for n in sizes:
        a, b = generate_cross(n), generate_x(n)
        flat_a, flat_b = flatten(a), flatten(b)
        assert is_close(mac(a, b), mac_flat(flat_a, flat_b))  # 같은 값을 내야 비교가 의미 있다
        start = time.perf_counter()
        for _ in range(repeat):
            mac(a, b)
        two_d = (time.perf_counter() - start) / repeat * 1000
        start = time.perf_counter()
        for _ in range(repeat):
            mac_flat(flat_a, flat_b)
        one_d = (time.perf_counter() - start) / repeat * 1000
        ratio = two_d / one_d if one_d > 0 else 0.0
        rows.append((n, two_d, one_d))
        print(f"{f'{n}×{n}':<10}{two_d:>12.4f}{one_d:>12.4f}{ratio:>7.2f}x")
    return rows


# ---------------------------------------------------------------- 실패 진단


def diagnose_failure(case):
    """FAIL 원인을 데이터/스키마, 수치 비교, 로직 셋 중 하나로 나눈다."""
    if case.get("error"):
        return {"category": "data_schema", "reason": case["error"]}
    if case["verdict"] == case["expected"]:
        return {"category": "none", "reason": "판정과 정답이 같다"}
    if case["verdict"] == UNDECIDED and not all(math.isfinite(x) for x in case["scores"]):
        return {"category": "numerical", "reason": "점수가 너무 커서 inf 로 넘쳐 비교할 수 없음(overflow)"}
    if case["verdict"] == UNDECIDED:
        return {
            "category": "numerical",
            "reason": f"두 점수 차이가 epsilon({EPSILON_TEXT}) 미만이라 동점(UNDECIDED) 처리",
        }
    return {"category": "logic", "reason": "점수 차이가 분명한데 정답과 다른 필터가 이겼다"}


# ---------------------------------------------------------------- 모드 1: 사용자 입력


def parse_row(line, n):
    """한 줄을 숫자 n 개로 바꾼다. 개수가 다르거나 숫자가 아니면 ValueError."""
    parts = line.split()
    if len(parts) != n:
        raise ValueError(f"입력 형식 오류: 각 줄에 {n}개의 숫자를 공백으로 구분해 입력하세요.")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        raise ValueError("입력 형식 오류: 숫자만 입력하세요.") from None
    if not all(math.isfinite(v) for v in values):
        raise ValueError("입력 형식 오류: nan·inf 는 점수를 비교할 수 없습니다. 보통 숫자를 입력하세요.")
    return values


def read_matrix(title, n, read=input):
    """n 줄을 받아 n×n 행렬을 만든다. 틀린 줄은 그 줄만 다시 받는다.

    첫 줄에 `cross` 나 `x` 를 넣으면 패턴 생성기가 n×n 패턴을 대신 만든다(보너스 2).
    """
    print(f"{title} ({n}줄 입력, 공백 구분 — 또는 cross / x 한 단어로 자동 생성)")
    matrix = []
    while len(matrix) < n:
        line = read()
        generated = GENERATORS.get(line.strip().lower()) if not matrix else None
        if generated:
            matrix = generated(n)
            print(f"  ✓ {line.strip()} 패턴 자동 생성")
            for row in matrix:
                print("  " + " ".join(f"{v:g}" for v in row))
            break
        try:
            matrix.append(parse_row(line, n))
        except ValueError as e:
            print(f"  {e} ({len(matrix) + 1}번째 줄을 다시 입력하세요)")
    return matrix


def run_user_mode(read=input):
    n = 3
    print(LINE)
    print("# [1] 필터 입력")
    print(LINE)
    filter_a = read_matrix("필터 A", n, read)
    filter_b = read_matrix("필터 B", n, read)
    print("✓ 필터 A, B 저장 완료")

    print(LINE)
    print("# [2] 패턴 입력")
    print(LINE)
    pattern = read_matrix("패턴", n, read)

    score_a = mac(pattern, filter_a)
    score_b = mac(pattern, filter_b)
    elapsed = measure_user_mac(pattern, filter_a, filter_b)
    verdict = decide(score_a, score_b, "A", "B")

    print(LINE)
    print("# [3] MAC 결과")
    print(LINE)
    print(f"A 점수: {score_a}")
    print(f"B 점수: {score_b}")
    print(f"연산 시간(평균/{REPEAT}회): {elapsed:.4f} ms")
    if verdict == UNDECIDED and not (math.isfinite(score_a) and math.isfinite(score_b)):
        print("판정: 판정 불가 (점수가 너무 커서 inf 로 넘침 — 비교할 수 없음)")
    elif verdict == UNDECIDED:
        print(f"판정: 판정 불가 (|A-B| < {EPSILON_TEXT})")
    else:
        print(f"판정: {verdict}")

    print_benchmark([n])


def measure_user_mac(pattern, filter_a, filter_b, repeat=REPEAT):
    """입력한 패턴으로 두 필터 MAC 를 repeat 번 돌린 평균(ms)."""
    start = time.perf_counter()
    for _ in range(repeat):
        mac(pattern, filter_a)
        mac(pattern, filter_b)
    return (time.perf_counter() - start) / repeat * 1000


# ---------------------------------------------------------------- 모드 2: data.json


def load_filters(raw_filters):
    """{'size_5': {'cross': [...], 'x': [...]}} → {5: {'Cross': [...], 'X': [...]}}.

    키 형식·라벨·크기가 맞지 않는 필터는 건너뛰고 이유를 출력한다.
    """
    filters = {}
    for key, pair in raw_filters.items():
        parts = key.split("_")
        n = parse_size(parts[1]) if len(parts) == 2 and parts[0] == "size" else None
        if n is None:
            print(f"✗ {key}: 필터 키 형식이 size_N 이 아님 — 건너뜀")
            continue
        if not isinstance(pair, dict):
            print(f"✗ {key}: 필터 항목이 {{cross, x}} 객체가 아님 — 건너뜀")
            continue
        loaded = {}
        for raw_label, matrix in pair.items():
            label = normalize_label(raw_label)
            if label is None:
                print(f"✗ {key}.{raw_label}: 알 수 없는 필터 라벨 — 건너뜀")
            elif not is_square(matrix, n):
                print(f"✗ {key}.{raw_label}: {n}×{n} 숫자 행렬이 아님 — 건너뜀")
            else:
                loaded[label] = matrix
        if CROSS in loaded and X in loaded:
            filters[n] = loaded
            print(f"✓ {key:<7} 필터 로드 완료 ({CROSS}, {X})")
        else:
            print(f"✗ {key}: Cross·X 필터가 모두 있어야 함 — 이 크기 패턴은 FAIL")
    return filters


def judge_case(key, entry, filters):
    """패턴 하나를 판정해 결과 dict 를 돌려준다. 문제가 있으면 error 에 이유를 담는다."""
    case = {"key": key, "expected": None, "verdict": None, "scores": None, "error": None}
    if not isinstance(entry, dict) or "input" not in entry or "expected" not in entry:
        case["error"] = "input·expected 키가 없음"
        return case
    case["expected"] = normalize_label(entry["expected"])
    if case["expected"] is None:
        case["error"] = f"expected 라벨을 알 수 없음({entry['expected']!r})"
        return case
    n = size_from_key(key)
    if n is None:
        case["error"] = "패턴 키 형식이 size_N_idx 가 아님"
        return case
    if n not in filters:
        case["error"] = f"size_{n} 필터가 없음"
        return case
    if not is_square(entry["input"], n):
        case["error"] = f"패턴이 {n}×{n} 유한 숫자 행렬이 아님(크기 불일치 또는 숫자 아닌 값)"
        return case
    cross_score = mac(entry["input"], filters[n][CROSS])
    x_score = mac(entry["input"], filters[n][X])
    case["scores"] = (cross_score, x_score)
    case["verdict"] = decide(cross_score, x_score, CROSS, X)
    return case


def print_case(case):
    print(f"--- {case['key']} ---")
    if case["error"]:
        print(f"판정: - | FAIL ({case['error']})")
        return
    cross_score, x_score = case["scores"]
    print(f"Cross 점수: {cross_score}")
    print(f"X 점수: {x_score}")
    result = "PASS" if case["verdict"] == case["expected"] else "FAIL"
    if result == "FAIL" and case["verdict"] == UNDECIDED:
        result = "FAIL (동점 규칙)"
    print(f"판정: {case['verdict']} | expected: {case['expected']} | {result}")


def run_json_mode(path=DATA_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"✗ {path} 파일이 없습니다.")
        return None
    except json.JSONDecodeError as e:
        print(f"✗ {path} 를 JSON 으로 읽을 수 없습니다: {e}")
        return None
    if not isinstance(data, dict) or not isinstance(data.get("filters"), dict) \
            or not isinstance(data.get("patterns"), dict):
        print("✗ data.json 최상위에 filters·patterns 객체가 있어야 합니다.")
        return None

    print(LINE)
    print("# [1] 필터 로드")
    print(LINE)
    filters = load_filters(data["filters"])

    print(LINE)
    print("# [2] 패턴 분석 (라벨 정규화 적용)")
    print(LINE)
    cases = []
    for key, entry in data["patterns"].items():
        case = judge_case(key, entry, filters)
        print_case(case)
        cases.append(case)

    times = print_benchmark(BENCH_SIZES)
    complexity = analyze_complexity(BENCH_SIZES, times)

    failures = [c for c in cases if c["error"] or c["verdict"] != c["expected"]]
    print(LINE)
    print("# [4] 결과 요약")
    print(LINE)
    print(f"총 테스트: {len(cases)}개")
    print(f"통과: {len(cases) - len(failures)}개")
    print(f"실패: {len(failures)}개")
    if failures:
        print("실패 케이스:")
        for case in failures:
            diagnosis = diagnose_failure(case)
            print(f"- {case['key']}: [{diagnosis['category']}] {diagnosis['reason']}")
    ratios = ", ".join(
        f"{a}→{b}: 시간 ×{t:.1f} / N² ×{o:.1f}"
        for (a, b), t, o in zip(
            complexity["size_pairs"], complexity["time_ratios"], complexity["ops_ratios"]
        )
    )
    print(f"복잡도: {complexity['estimated_order']} ({ratios})")
    compare_flat(BENCH_SIZES)
    return {"cases": cases, "times": times, "complexity": complexity}


# ---------------------------------------------------------------- 진입점


def choose_mode(read=input):
    while True:
        choice = read("선택: ").strip()
        if choice in ("1", "2"):
            return choice
        print("1 또는 2 를 입력하세요.")


def main():
    print("=== Mini NPU Simulator ===")
    print()
    print("[모드 선택]")
    print("1. 사용자 입력 (3x3)")
    print("2. data.json 분석")
    try:
        if choose_mode() == "1":
            run_user_mode()
        else:
            run_json_mode()
    except (EOFError, KeyboardInterrupt):
        print("\n입력이 끝나 프로그램을 종료합니다.")


if __name__ == "__main__":
    main()
