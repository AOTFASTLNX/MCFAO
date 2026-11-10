"""Summarize bounded Mac JVMTI diagnostics; shallow objects and samples are distinct."""
import argparse
import collections
import json
from pathlib import Path

from bootstrap_toolchain import sha256


def summarize(text):
    samples={};frames=collections.defaultdict(list);objects=[];oom_frames=[];statuses={}
    snapshots=collections.OrderedDict()
    lines=text.splitlines()
    # A live diagnostic file may end halfway through a line.
    if text and not text.endswith('\n'):lines=lines[:-1]
    for line in lines:
        x=line.split('\t')
        if x[0]=='ALLOC':
            if len(x)!=5 or int(x[1]) in samples:raise ValueError('Invalid/duplicate allocation sample')
            samples[int(x[1])]={'bytes':int(x[2]),'class':x[3],'stackStatus':int(x[4])}
        elif x[0]=='ALLOC_FRAME':
            if len(x)!=5:raise ValueError('Invalid allocation frame')
            frames[int(x[1])].append({'class':x[2],'method':x[3],'bci':int(x[4])})
        elif x[0]=='CLASS':
            if len(x)!=5 or any(int(v)<0 for v in x[2:]):raise ValueError('Invalid shallow census')
            objects.append({'class':x[1],'objects':int(x[2]),'shallowBytes':int(x[3]),'arrayElements':int(x[4])})
        elif x[0]=='FRAME':oom_frames.append({'class':x[1],'method':x[2],'signature':x[3],'bci':int(x[4])})
        elif x[0] in ('ITERATION_STATUS','STACK_STATUS','CLASSES_STATUS'):statuses[x[0]]=[int(v) for v in x[1:]]
        elif x[0]=='SNAPSHOT_BEGIN':
            if len(x)!=3:raise ValueError('Invalid snapshot header')
            if x[1] in snapshots:raise ValueError('Duplicate snapshot label')
            snapshots[x[1]]={'label':x[1],'startedAtMillis':int(x[2]),'classes':[]}
        elif x[0]=='SNAPSHOT_STATUS':
            if len(x)!=5:raise ValueError('Invalid snapshot status')
            snapshots.setdefault(x[1],{'label':x[1],'startedAtMillis':None,'classes':[]})['status']=[int(v) for v in x[2:]]
        elif x[0]=='SNAPSHOT_CLASS':
            if len(x)!=6 or any(int(v)<0 for v in x[3:]) or x[1] not in snapshots:raise ValueError('Invalid snapshot class')
            snapshots[x[1]]['classes'].append({'class':x[2],'objects':int(x[3]),'shallowBytes':int(x[4]),'arrayElements':int(x[5])})
        elif x[0]=='SNAPSHOT_LARGE':
            if len(x)!=4 or int(x[3])<0 or x[1] not in snapshots:raise ValueError('Invalid snapshot large-array record')
            snapshots[x[1]].setdefault('largestArrays',[]).append({'class':x[2],'elements':int(x[3])})
        elif x[0]=='SNAPSHOT_END':
            if x[1] not in snapshots:raise ValueError('Snapshot end without header')
            snapshots[x[1]]['completed']=True
    callers=collections.Counter();types=collections.Counter()
    for i,sample in samples.items():
        types[sample['class']]+=1
        for frame in frames[i]:
            if frame['class'].startswith('Lcom/oracle/graal/pointsto/'):
                callers[frame['class']+'.'+frame['method']]+=1;break
    scheduled=[]
    for snapshot in snapshots.values():
        ordered=sorted(snapshot['classes'],key=lambda x:x['shallowBytes'],reverse=True)
        scheduled.append({'label':snapshot['label'],'startedAtMillis':snapshot['startedAtMillis'],
            'status':snapshot.get('status'),'completed':snapshot.get('completed',False),
            'objectsCounted':sum(x['objects'] for x in snapshot['classes']),
            'shallowBytesCounted':sum(x['shallowBytes'] for x in snapshot['classes']),
            'largestShallowClasses':ordered[:15],
            'largestArrays':sorted(snapshot.get('largestArrays',[]),key=lambda x:-x['elements'])[:12]})
    return {'allocationSamples':len(samples),'sampledClasses':types.most_common(20),
            'firstPointsToFramePerSample':callers.most_common(20),
            'lastAllocationSamples':[{**samples[i],'frames':frames[i]} for i in sorted(samples)[-10:]],
            'censusCompleted':'CENSUS_END' in lines and statuses.get('ITERATION_STATUS')==[0,0],
            'statuses':statuses,'objectsCounted':sum(x['objects'] for x in objects),
            'shallowBytesCounted':sum(x['shallowBytes'] for x in objects),
            'largestShallowClasses':sorted(objects,key=lambda x:x['shallowBytes'],reverse=True)[:20],
            'unknownClassObjects':sum(x['objects'] for x in objects if x['class']=='<unknown>'),
            'oomStack':oom_frames,'scheduledSnapshots':scheduled,
            'scope':'Mac build-JVM only; allocation sample counts are not allocated/retained bytes; '
                    'heap iteration includes unreachable objects and may occur after peak memory; '
                    'each scheduled snapshot stops the world and perturbs the run it measures; '
                    'no root paths or iOS measurements'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.input.stat().st_size>64*1024**2:parser.error('Diagnostic exceeds file budget')
    result=summarize(args.input.read_text());result['inputSHA256']=sha256(args.input)
    with args.output.open('x') as file:json.dump(result,file,indent=2);file.write('\n')
    print(json.dumps({k:result[k] for k in ['allocationSamples','censusCompleted','objectsCounted','shallowBytesCounted','firstPointsToFramePerSample']},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
