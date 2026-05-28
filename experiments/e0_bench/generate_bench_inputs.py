"""Generate bench_inputs.json — extract .gfso criteria from LiveCodeBench medium problems.

Criteria fields:
  - input + expected → exact output check
  - input only → crash check
  - n + timeout → performance check
"""
import io
import sys
import json
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from huggingface_hub import hf_hub_download


def load_medium_problems():
    f = hf_hub_download('livecodebench/code_generation_lite', 'test.jsonl', repo_type='dataset')
    problems = []
    with open(f, encoding='utf-8') as fp:
        for line in fp:
            p = json.loads(line)
            if p['difficulty'] == 'medium':
                problems.append(p)
    return problems


def clean_content(p):
    c = re.sub(r'<[^>]+>', '', p['question_content'])
    return c.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('\u200b', '')


def extract_max_size(content):
    for m in re.finditer(r'(?:length|\.length|size|\.size)\s*<=?\s*10\s*\^\s*\{?(\d+)\}?', content, re.I):
        return 10 ** int(m.group(1))
    for m in re.finditer(r'1\s*<=?\s*n\s*<=?\s*10\s*\^\s*\{?(\d+)\}?', content, re.I):
        return 10 ** int(m.group(1))
    for m in re.finditer(r'(?:length|\.length|size)\s*<=?\s*(\d{4,})', content, re.I):
        return int(m.group(1))
    for m in re.finditer(r'10\s*\^\s*\{?(\d+)\}?', content):
        exp = int(m.group(1))
        if 3 <= exp <= 6:
            return 10 ** exp
    return None


def split_codeforces_examples(pub):
    """Split Codeforces multi-test into individual (input, output) pairs."""
    results = []
    for tc in pub:
        in_lines = tc['input'].strip().split('\n')
        out_lines = tc['output'].strip().split('\n')
        first = in_lines[0].strip()
        if first.isdigit() and int(first) == len(out_lines) and int(first) > 1:
            # Multi-test: t matches output line count
            t = int(first)
            remaining = in_lines[1:]
            lines_per_case = len(remaining) // t if t > 0 else 1
            for i in range(min(t, 5)):  # max 5 examples
                start = i * lines_per_case
                case_in = '\n'.join(remaining[start:start + lines_per_case])
                case_out = out_lines[i] if i < len(out_lines) else ""
                # Wrap with t=1 for standalone execution
                results.append((f"1\n{case_in}", case_out))
        else:
            results.append((tc['input'].rstrip('\n'), tc['output'].rstrip('\n')))
    return results


def make_edge_input(pub, platform):
    """Minimal valid input from example format + constraints."""
    if not pub:
        return None
    lines = pub[0]['input'].strip().split('\n')
    first = lines[0].strip()
    rest = lines[1:]

    if platform == 'codeforces' and first.isdigit() and int(first) > 1:
        # Multi-test: t=1 + minimal case
        case_lines = lines[1:1 + (len(lines) - 1) // int(first)]
        minimal = []
        for line in case_lines:
            parts = line.strip().split()
            if all(p.lstrip('-').isdigit() for p in parts):
                minimal.append(' '.join(['1'] * len(parts)))
            elif line.strip().isalpha():
                minimal.append('a')
            else:
                minimal.append(line.strip())
        return '1\n' + '\n'.join(minimal)

    if first.startswith('[['):
        edge_first = '[[1]]'
    elif first.startswith('['):
        edge_first = '[1]'
    elif first.startswith('"'):
        edge_first = '"a"'
    else:
        parts = first.split()
        edge_first = ' '.join(['1'] * len(parts))

    edge_rest = []
    for line in rest:
        line = line.strip()
        if line.startswith('['):
            edge_rest.append('[1]')
        elif line.startswith('"'):
            edge_rest.append('"a"')
        elif line.replace('-', '').replace(' ', '').isdigit():
            parts = line.split()
            edge_rest.append(' '.join(['1'] * len(parts)))
        else:
            edge_rest.append(line)

    return '\n'.join([edge_first] + edge_rest)


def main():
    problems = load_medium_problems()
    entries = []

    for i, p in enumerate(problems):
        pub = json.loads(p['public_test_cases'])
        content = clean_content(p)
        platform = p.get('platform', 'leetcode')
        criteria = []

        # 1. Examples — original format (including batch for Codeforces)
        for j, tc in enumerate(pub):
            criteria.append({
                "name": f"example_{j+1}",
                "input": tc['input'].rstrip('\n'),
                "expected": tc['output'].rstrip('\n'),
            })

        # 2. Performance
        max_size = extract_max_size(content)
        if max_size and max_size >= 1000:
            criteria.append({"name": "performance", "n": max_size, "timeout": 10})

        # 3. Edge — only for simple formats where min input is predictable
        if platform == 'leetcode':
            edge = make_edge_input(pub, platform)
            if edge:
                criteria.append({"name": "edge_min", "input": edge})

        entries.append({"problem_index": i, "criteria": criteria, "neglected": []})

    with open('data/bench_inputs.json', 'w', encoding='utf-8') as fp:
        json.dump(entries, fp, indent=2, ensure_ascii=False)

    print(f"Generated {len(entries)} entries → bench_inputs.json")
    has_perf = sum(1 for e in entries if any('n' in c for c in e['criteria']))
    print(f"With performance: {has_perf}/{len(entries)}")


if __name__ == '__main__':
    main()
