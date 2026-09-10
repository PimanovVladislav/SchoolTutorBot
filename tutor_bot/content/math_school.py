"""Школьная математика: стартовый контент для 6–9 классов."""

from __future__ import annotations

MATH_SCHOOL_TOPICS: list[dict] = [
    {
        "grade": 6,
        "slug": "fraction-addition",
        "title": "Сложение и вычитание обыкновенных дробей",
        "summary": "Общий знаменатель, НОК, сложение и вычитание дробей.",
        "sort_order": 10,
        "theory": (
            "<b>Сложение и вычитание обыкновенных дробей</b>\n\n"
            "Дроби можно складывать и вычитать, только когда у них "
            "<b>одинаковый знаменатель</b>.\n\n"
            "1) Если знаменатели разные, находим <b>НОК</b> знаменателей — "
            "это новый общий знаменатель.\n"
            "2) Домножаем числитель и знаменатель каждой дроби на столько, "
            "чтобы знаменатель стал общим.\n"
            "3) Складываем или вычитаем <i>числители</i>, знаменатель не трогаем.\n"
            "4) Сокращаем результат, если можно.\n\n"
            "<b>Пример.</b> 1/2 + 1/3\n"
            "НОК(2, 3) = 6\n"
            "1/2 = 3/6,  1/3 = 2/6\n"
            "3/6 + 2/6 = 5/6\n\n"
            "Смешанное число: 1 1/2 = 3/2. Иногда удобнее сначала перевести "
            "всё в неправильные дроби.\n\n"
            "Ответ пиши <b>обыкновенной дробью</b> вроде <code>5/6</code> "
            "или целым числом."
        ),
        "problems": [
            {
                "kind": "training",
                "answer_type": "fraction",
                "prompt": "Вычисли: 1/4 + 1/2. Ответ запиши дробью.",
                "correct_answer": "3/4",
                "hint": "Приведи к знаменателю 4: 1/2 = 2/4.",
                "solution": (
                    "НОК(4, 2) = 4.\n"
                    "1/2 = 2/4.\n"
                    "1/4 + 2/4 = 3/4."
                ),
                "sort_order": 1,
            },
            {
                "kind": "training",
                "answer_type": "fraction",
                "prompt": "Вычисли: 5/6 − 1/3.",
                "correct_answer": "1/2",
                "hint": "1/3 = 2/6. Не забудь сократить ответ.",
                "solution": (
                    "НОК(6, 3) = 6.\n"
                    "1/3 = 2/6.\n"
                    "5/6 − 2/6 = 3/6 = 1/2."
                ),
                "sort_order": 2,
            },
            {
                "kind": "training",
                "answer_type": "fraction",
                "prompt": "Вычисли: 2/5 + 3/10.",
                "correct_answer": "7/10",
                "hint": "Общий знаменатель — 10.",
                "solution": "2/5 = 4/10. 4/10 + 3/10 = 7/10.",
                "sort_order": 3,
            },
            {
                "kind": "training",
                "answer_type": "fraction",
                "prompt": "Вычисли: 1/2 + 1/3 + 1/6.",
                "correct_answer": "1",
                "hint": "Общий знаменатель всех трёх дробей — 6.",
                "solution": (
                    "1/2 = 3/6, 1/3 = 2/6, 1/6 = 1/6.\n"
                    "3/6 + 2/6 + 1/6 = 6/6 = 1."
                ),
                "sort_order": 4,
            },
            {
                "kind": "assessment",
                "answer_type": "fraction",
                "prompt": "Вычисли: 7/12 − 1/4.",
                "correct_answer": "1/3",
                "hint": "1/4 = 3/12.",
                "solution": "7/12 − 3/12 = 4/12 = 1/3.",
                "sort_order": 1,
            },
            {
                "kind": "assessment",
                "answer_type": "fraction",
                "prompt": "Вычисли: 3/8 + 1/6.",
                "correct_answer": "13/24",
                "hint": "НОК(8, 6) = 24.",
                "solution": (
                    "3/8 = 9/24, 1/6 = 4/24.\n"
                    "9/24 + 4/24 = 13/24."
                ),
                "sort_order": 2,
            },
            {
                "kind": "assessment",
                "answer_type": "fraction",
                "prompt": "Вычисли: 5/6 − 2/9.",
                "correct_answer": "11/18",
                "hint": "НОК(6, 9) = 18.",
                "solution": (
                    "5/6 = 15/18, 2/9 = 4/18.\n"
                    "15/18 − 4/18 = 11/18."
                ),
                "sort_order": 3,
            },
            {
                "kind": "reinforcement",
                "answer_type": "fraction",
                "prompt": "Закрепление. Вычисли: 2/3 + 1/6.",
                "correct_answer": "5/6",
                "hint": "2/3 = 4/6.",
                "solution": "4/6 + 1/6 = 5/6.",
                "sort_order": 1,
            },
            {
                "kind": "reinforcement",
                "answer_type": "fraction",
                "prompt": "Закрепление. Вычисли: 4/5 − 1/2.",
                "correct_answer": "3/10",
                "hint": "Общий знаменатель — 10.",
                "solution": "8/10 − 5/10 = 3/10.",
                "sort_order": 2,
            },
        ],
    },
    {
        "grade": 7,
        "slug": "linear-equations",
        "title": "Линейные уравнения",
        "summary": "Уравнения вида ax + b = c, перенос слагаемых, деление.",
        "sort_order": 10,
        "theory": (
            "<b>Линейные уравнения</b>\n\n"
            "Линейное уравнение относительно x — это уравнение, которое "
            "приводится к виду <code>ax + b = 0</code> или "
            "<code>ax = c</code>.\n\n"
            "<b>Правила:</b>\n"
            "• слагаемое можно переносить в другую часть, меняя знак;\n"
            "• обе части можно умножать или делить на одно и то же "
            "число (кроме нуля);\n"
            "• скобки раскрываем, подобные приводим.\n\n"
            "<b>Пример.</b> 3x − 5 = 7\n"
            "3x = 7 + 5\n"
            "3x = 12\n"
            "x = 4\n\n"
            "Ответ — <b>число</b>. Если получилась дробь, пиши её как "
            "<code>2/3</code> или <code>0.5</code>."
        ),
        "problems": [
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Реши уравнение: x + 7 = 12. Чему равен x?",
                "correct_answer": "5",
                "hint": "Перенеси 7 вправо с минусом.",
                "solution": "x = 12 − 7 = 5.",
                "sort_order": 1,
            },
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Реши уравнение: 4x = 20.",
                "correct_answer": "5",
                "hint": "Раздели обе части на 4.",
                "solution": "x = 20 / 4 = 5.",
                "sort_order": 2,
            },
            {
                "kind": "training",
                "answer_type": "fraction",
                "prompt": "Реши уравнение: 2x − 3 = 5.",
                "correct_answer": "4",
                "hint": "Сначала перенеси −3.",
                "solution": "2x = 8, x = 4.",
                "sort_order": 3,
            },
            {
                "kind": "training",
                "answer_type": "fraction",
                "prompt": "Реши уравнение: 3x + 2 = 8.",
                "correct_answer": "2",
                "hint": "3x = 6.",
                "solution": "3x = 8 − 2 = 6, x = 2.",
                "sort_order": 4,
            },
            {
                "kind": "assessment",
                "answer_type": "fraction",
                "prompt": "Реши уравнение: 5x − 4 = 11.",
                "correct_answer": "3",
                "hint": "5x = 15.",
                "solution": "5x = 15, x = 3.",
                "sort_order": 1,
            },
            {
                "kind": "assessment",
                "answer_type": "fraction",
                "prompt": "Реши уравнение: 2(x − 3) = 8.",
                "correct_answer": "7",
                "hint": "Сначала раздели обе части на 2 или раскрой скобку.",
                "solution": "x − 3 = 4, x = 7.",
                "sort_order": 2,
            },
            {
                "kind": "assessment",
                "answer_type": "fraction",
                "prompt": "Реши уравнение: 6x + 5 = 2x − 7.",
                "correct_answer": "-3",
                "hint": "Собери x влево, числа вправо.",
                "solution": (
                    "6x − 2x = −7 − 5\n"
                    "4x = −12\n"
                    "x = −3"
                ),
                "sort_order": 3,
            },
            {
                "kind": "reinforcement",
                "answer_type": "fraction",
                "prompt": "Закрепление. Реши: 7x = 21.",
                "correct_answer": "3",
                "hint": "Раздели обе части на 7.",
                "solution": "x = 3.",
                "sort_order": 1,
            },
            {
                "kind": "reinforcement",
                "answer_type": "fraction",
                "prompt": "Закрепление. Реши: 4x + 1 = 13.",
                "correct_answer": "3",
                "hint": "4x = 12.",
                "solution": "x = 3.",
                "sort_order": 2,
            },
        ],
    },
    {
        "grade": 8,
        "slug": "quadratic-equations",
        "title": "Квадратные уравнения",
        "summary": "Дискриминант и формула корней квадратного уравнения.",
        "sort_order": 10,
        "theory": (
            "<b>Квадратные уравнения</b>\n\n"
            "Общий вид: <code>ax² + bx + c = 0</code>, где a ≠ 0.\n\n"
            "<b>Дискриминант:</b> D = b² − 4ac\n\n"
            "• если D &gt; 0 — два различных корня:\n"
            "  x = (−b ± √D) / (2a)\n"
            "• если D = 0 — один корень (два совпавших):\n"
            "  x = −b / (2a)\n"
            "• если D &lt; 0 — действительных корней нет.\n\n"
            "<b>Пример.</b> x² − 5x + 6 = 0\n"
            "D = 25 − 24 = 1\n"
            "x = (5 ± 1) / 2\n"
            "x₁ = 3, x₂ = 2\n\n"
            "Если корней два, напиши их через точку с запятой, порядок "
            "не важен: <code>2; 3</code>."
        ),
        "problems": [
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Найди дискриминант уравнения x² − 5x + 6 = 0.",
                "correct_answer": "1",
                "hint": "D = b² − 4ac, здесь a=1, b=−5, c=6.",
                "solution": "D = (−5)² − 4·1·6 = 25 − 24 = 1.",
                "sort_order": 1,
            },
            {
                "kind": "training",
                "answer_type": "numbers",
                "prompt": "Реши уравнение: x² − 5x + 6 = 0. Запиши оба корня.",
                "correct_answer": "2;3",
                "hint": "D = 1, x = (5 ± 1) / 2.",
                "solution": "x₁ = 6/2 = 3, x₂ = 4/2 = 2. Корни: 2 и 3.",
                "sort_order": 2,
            },
            {
                "kind": "training",
                "answer_type": "numbers",
                "prompt": "Реши уравнение: x² − 4x = 0.",
                "correct_answer": "0;4",
                "hint": "Вынеси x за скобку.",
                "solution": "x(x − 4) = 0 → x = 0 или x = 4.",
                "sort_order": 3,
            },
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Реши уравнение: x² − 9 = 0. Укажи положительный корень.",
                "correct_answer": "3",
                "hint": "Разность квадратов: (x − 3)(x + 3) = 0.",
                "solution": "x = 3 или x = −3. Положительный корень: 3.",
                "sort_order": 4,
            },
            {
                "kind": "assessment",
                "answer_type": "numbers",
                "prompt": "Реши: x² − 3x − 10 = 0.",
                "correct_answer": "-2;5",
                "hint": "D = 9 + 40 = 49.",
                "solution": (
                    "D = 49, √D = 7.\n"
                    "x = (3 ± 7) / 2\n"
                    "x₁ = 5, x₂ = −2."
                ),
                "sort_order": 1,
            },
            {
                "kind": "assessment",
                "answer_type": "number",
                "prompt": "Реши: x² + 6x + 9 = 0. Запиши корень.",
                "correct_answer": "-3",
                "hint": "Это полный квадрат (x + 3)².",
                "solution": "D = 0, x = −6 / 2 = −3.",
                "sort_order": 2,
            },
            {
                "kind": "assessment",
                "answer_type": "numbers",
                "prompt": "Реши: 2x² − 8x + 6 = 0.",
                "correct_answer": "1;3",
                "hint": "Можно сначала разделить уравнение на 2.",
                "solution": (
                    "x² − 4x + 3 = 0\n"
                    "D = 16 − 12 = 4\n"
                    "x = (4 ± 2) / 2 → 3 и 1."
                ),
                "sort_order": 3,
            },
            {
                "kind": "reinforcement",
                "answer_type": "numbers",
                "prompt": "Закрепление. Реши: x² − 6x + 8 = 0.",
                "correct_answer": "2;4",
                "hint": "Подбери числа с суммой 6 и произведением 8.",
                "solution": "Корни 2 и 4: (x − 2)(x − 4) = 0.",
                "sort_order": 1,
            },
            {
                "kind": "reinforcement",
                "answer_type": "number",
                "prompt": "Закрепление. Найди D для x² + 2x + 5 = 0.",
                "correct_answer": "-16",
                "hint": "D = 4 − 20.",
                "solution": "D = 4 − 20 = −16. Действительных корней нет, но D = −16.",
                "sort_order": 2,
            },
        ],
    },
    {
        "grade": 9,
        "slug": "pythagorean-theorem",
        "title": "Теорема Пифагора",
        "summary": "Связь сторон прямоугольного треугольника, гипотенуза и катеты.",
        "sort_order": 10,
        "theory": (
            "<b>Теорема Пифагора</b>\n\n"
            "В прямоугольном треугольнике квадрат гипотенузы равен сумме "
            "квадратов катетов:\n\n"
            "<code>c² = a² + b²</code>\n\n"
            "Гипотенуза — сторона напротив прямого угла, всегда самая длинная.\n\n"
            "Отсюда:\n"
            "• гипотенуза c = √(a² + b²)\n"
            "• катет a = √(c² − b²)\n\n"
            "<b>Пример.</b> Катеты 3 и 4.\n"
            "c = √(9 + 16) = √25 = 5.\n\n"
            "Это «египетский» треугольник 3-4-5. Запомни ещё 5-12-13 и 6-8-10.\n\n"
            "Ответ — <b>число</b> (длина стороны)."
        ),
        "problems": [
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Катеты 6 и 8. Найди гипотенузу.",
                "correct_answer": "10",
                "hint": "Это удвоенный треугольник 3-4-5.",
                "solution": "c = √(36 + 64) = √100 = 10.",
                "sort_order": 1,
            },
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Гипотенуза 13, катет 5. Найди второй катет.",
                "correct_answer": "12",
                "hint": "a = √(c² − b²).",
                "solution": "a = √(169 − 25) = √144 = 12.",
                "sort_order": 2,
            },
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Катеты 5 и 12. Найди гипотенузу.",
                "correct_answer": "13",
                "hint": "Классическая тройка 5-12-13.",
                "solution": "c = √(25 + 144) = √169 = 13.",
                "sort_order": 3,
            },
            {
                "kind": "training",
                "answer_type": "number",
                "prompt": "Гипотенуза 10, катет 6. Найди второй катет.",
                "correct_answer": "8",
                "hint": "√(100 − 36).",
                "solution": "a = √(100 − 36) = √64 = 8.",
                "sort_order": 4,
            },
            {
                "kind": "assessment",
                "answer_type": "number",
                "prompt": "Катеты 9 и 12. Найди гипотенузу.",
                "correct_answer": "15",
                "hint": "Утроенный 3-4-5.",
                "solution": "c = √(81 + 144) = √225 = 15.",
                "sort_order": 1,
            },
            {
                "kind": "assessment",
                "answer_type": "number",
                "prompt": "Гипотенуза 25, катет 7. Найди второй катет.",
                "correct_answer": "24",
                "hint": "√(625 − 49) = √576.",
                "solution": "a = √(625 − 49) = √576 = 24.",
                "sort_order": 2,
            },
            {
                "kind": "assessment",
                "answer_type": "number",
                "prompt": "Катеты 8 и 15. Найди гипотенузу.",
                "correct_answer": "17",
                "hint": "64 + 225 = 289.",
                "solution": "c = √(64 + 225) = √289 = 17.",
                "sort_order": 3,
            },
            {
                "kind": "reinforcement",
                "answer_type": "number",
                "prompt": "Закрепление. Катеты 3 и 4. Гипотенуза?",
                "correct_answer": "5",
                "hint": "Самый известный прямоугольный треугольник.",
                "solution": "√(9+16)=5.",
                "sort_order": 1,
            },
            {
                "kind": "reinforcement",
                "answer_type": "number",
                "prompt": "Закрепление. Гипотенуза 13, катет 12. Второй катет?",
                "correct_answer": "5",
                "hint": "Тройка 5-12-13.",
                "solution": "√(169 − 144) = √25 = 5.",
                "sort_order": 2,
            },
        ],
    },
]
