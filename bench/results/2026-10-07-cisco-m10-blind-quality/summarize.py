"""After review lock and unsealing: produce machine-readable metrics and tables."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
key=json.loads((HERE/'unsealed/mapping.json').read_text())
commit=(HERE/'mapping-commitment.sha256').read_text().strip()
assert hashlib.sha256((HERE/'unsealed/mapping.json').read_bytes()).hexdigest()==commit
lock=json.loads((HERE/'review-lock.json').read_text())
for name,sha in lock['sha256'].items():
    assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==sha, name
reviews=json.loads((HERE/'reviews.json').read_text())
suite=json.loads((HERE/'suite.json').read_text())
assert len(reviews)==len(suite)==32
rows=[]
for block,model in enumerate(key['order']):
    folder=HERE/'unsealed'/f'block-{block}'
    telemetry=[json.loads(line) for line in (folder/'telemetry.jsonl').read_text().splitlines()]
    for c in suite:
        id=c['id'];r=json.loads((folder/f'{id}.json').read_text())
        label='A' if key['pairs'][id]==block else 'B'
        pair=json.loads((HERE/'blind'/f'{id}.json').read_text())
        assert pair[label]['content']==r['content'] and pair[label]['reasoning']==r['reasoning']
        t=r['final']['timings'];samples=[s for s in telemetry if s['phase']==id]
        assert samples, id
        review=next(x for x in reviews if x['id']==id)
        quality=review[label]
        row=dict(id=id,category=c['category'],model=model,label=label,
            winner=review['winner'],won=review['winner']==label,tie=review['winner']=='tie',
            objective_error=bool(quality['objective_errors']),
            objective_error_count=len(quality['objective_errors']),
            corrected_error_count=len(quality['corrected_errors']),
            final_conclusion_correct=quality['final_conclusion_correct'],
            instruction_error_count=len(quality['instruction_errors']),
            finish_reason=r['final']['choices'][0]['finish_reason'],
            prompt_tokens=r['final']['usage']['prompt_tokens'],completion_tokens=r['final']['usage']['completion_tokens'],
            cached_tokens=t.get('cache_n',0),decode_tps=t['predicted_per_second'],prompt_tps=t['prompt_per_second'],
            decode_ms=t['predicted_ms'],prompt_ms=t['prompt_ms'],prompt_n=t['prompt_n'],
            ttft_s=r['first_token_s'],wall_s=r['wall_s'],telemetry_samples=len(samples),
            engine_rss_peak_gib=max(s.get('engine_rss_bytes',0) for s in samples)/2**30,
            process_rss_peak_gib=max(s.get('rss_bytes',0) for s in samples)/2**30,
            guest_used_peak_gib=max(s['ram_used_bytes'] for s in samples)/2**30,
            guest_available_min_gib=min(s['ram_available_bytes'] for s in samples)/2**30,
            guest_unavailable_peak_gib=max(s['ram_total_bytes']-s['ram_available_bytes'] for s in samples)/2**30,
            guest_total_gib=samples[0]['ram_total_bytes']/2**30,
            swap_peak_bytes=max(s['swap_used_bytes'] for s in samples),
            swap_in_delta_bytes=max(s['swap_sin_bytes'] for s in samples)-min(s['swap_sin_bytes'] for s in samples),
            swap_out_delta_bytes=max(s['swap_sout_bytes'] for s in samples)-min(s['swap_sout_bytes'] for s in samples),
            vram_peak_mib=[max(g['memory_mib'] for s in samples for g in s.get('gpus',[]) if g['index']==i) for i in range(8)])
        rows.append(row)
(HERE/'metrics.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
with (HERE/'metrics.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
summary={}
for model in ['Q4','Q8']:
    rr=[r for r in rows if r['model']==model]
    summary[model]=dict(wins=sum(r['won'] for r in rr),ties=sum(r['tie'] for r in rr),
        objective_error_answers=sum(r['objective_error'] for r in rr),
        objective_errors=sum(r['objective_error_count'] for r in rr),
        corrected_error_answers=sum(r['corrected_error_count']>0 for r in rr),
        instruction_error_answers=sum(r['instruction_error_count']>0 for r in rr),
        truncated_answers=sum(r['finish_reason']=='length' for r in rr),
        mean_decode_tps=statistics.mean(r['decode_tps'] for r in rr),
        mean_prompt_tps=statistics.mean(r['prompt_tps'] for r in rr),
        weighted_prompt_tps=sum(r['prompt_n'] for r in rr)/(sum(r['prompt_ms'] for r in rr)/1000),
        mean_ttft_s=statistics.mean(r['ttft_s'] for r in rr),
        mean_wall_s=statistics.mean(r['wall_s'] for r in rr),
        mean_completion_tokens=statistics.mean(r['completion_tokens'] for r in rr),
        max_engine_rss_gib=max(r['engine_rss_peak_gib'] for r in rr),
        min_guest_available_gib=min(r['guest_available_min_gib'] for r in rr),
        max_swap_bytes=max(r['swap_peak_bytes'] for r in rr),
        max_vram_mib=[max(r['vram_peak_mib'][i] for r in rr) for i in range(8)])
# Engine decode counters can include speculative tokens differently from API usage.
# Reconstruct weighted engine rate from its reported per-request rate and time.
for model in ['Q4','Q8']:
    rr=[r for r in rows if r['model']==model]
    summary[model]['weighted_engine_decode_tps']=sum(r['decode_tps']*r['decode_ms'] for r in rr)/sum(r['decode_ms'] for r in rr)
comparisons={}
for metric in ['decode_tps','prompt_tps','ttft_s','wall_s']:
    ratios=[]
    for c in suite:
        pair={r['model']:r for r in rows if r['id']==c['id']}
        ratios.append(pair['Q8'][metric]/pair['Q4'][metric])
    comparisons[metric]=dict(mean_q8_q4_ratio=statistics.mean(ratios),median_q8_q4_ratio=statistics.median(ratios),
                            mean_percent_change=100*(statistics.mean(ratios)-1))
summary['paired_performance']=comparisons
categories={}
for cat in dict.fromkeys(c['category'] for c in suite):
    rr=[r for r in rows if r['category']==cat]
    categories[cat]=dict(Q4_wins=sum(r['won'] for r in rr if r['model']=='Q4'),
                        Q8_wins=sum(r['won'] for r in rr if r['model']=='Q8'),
                        ties=sum(r['tie'] for r in rr if r['model']=='Q4'))
summary['categories']=categories
full_ids={c['id'] for c in suite if not any(r['finish_reason']=='length' for r in rows if r['id']==c['id'])}
summary['sensitivity_without_truncated_pairs']=dict(pairs=len(full_ids),
    Q4_wins=sum(r['won'] for r in rows if r['model']=='Q4' and r['id'] in full_ids),
    Q8_wins=sum(r['won'] for r in rows if r['model']=='Q8' and r['id'] in full_ids),
    ties=sum(r['tie'] for r in rows if r['model']=='Q4' and r['id'] in full_ids))
(HERE/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
lines=['| Id | Kategori | Vinnare | Q4 sakfel | Q8 sakfel | Q4 tok/s | Q8 tok/s | Q4 TTFT s | Q8 TTFT s |',
       '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
for c in suite:
    pair={r['model']:r for r in rows if r['id']==c['id']};a,b=pair['Q4'],pair['Q8']
    winner='Oavgjort' if a['tie'] else ('Q4' if a['won'] else 'Q8')
    lines.append(f"| {c['id']} | {c['category']} | {winner} | {a['objective_error_count']} | {b['objective_error_count']} | {a['decode_tps']:.2f} | {b['decode_tps']:.2f} | {a['ttft_s']:.2f} | {b['ttft_s']:.2f} |")
(HERE/'summary-table.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2,ensure_ascii=False))
