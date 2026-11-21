import json,subprocess,re
import os
R='rec/';A=os.environ.get('AUD','audio/');C='cards/';EXT=os.environ.get('EXT','aiff')
m=dict(json.load(open(R+'marks.json')))
import os; v0=float(os.environ.get('SYNC','85'))/30+0.1-m['sync']  # video time = mark + v0
vt=lambda k:m[k]+v0
dur=lambda f:float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f]))
segs=[('card','title',4.5)]
PAD={'s5':float(os.environ.get('PAD5','2.2'))}
for a,b in [('s1','s2'),('s2','s3'),('s3','s4'),('s4','s5'),('s5','end')]:
    segs.append(('vid',(vt(a),vt(b)),vt(b)-vt(a)+PAD.get(a,0),PAD.get(a,0)))
segs+= [('card','results',dur(A+'s6.'+EXT)+0.8+0.5),('card','closing',dur(A+'s7.'+EXT)+0.6+1.0)]
# scene starts in output
starts=[];t=0
for s in segs: starts.append(t);t+=s[2]
total=t
# audio placement: scene index for each narration clip
aud={1:starts[0]+0.6,2:starts[2]+0.4,3:starts[3]+0.4,4:starts[4]+0.6,5:starts[5]+5.0,6:starts[6]+0.8,7:starts[7]+0.6}
print('total',round(total,2),{k:round(v,2) for k,v in aud.items()})
# build video parts
parts=[]
for i,s in enumerate(segs):
    out=f'part{i}.mp4'
    if s[0]=='card':
        subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-framerate','30','-i',C+s[1]+'.png','-t',str(s[2]),'-vf','scale=1920:1080,format=yuv420p','-c:v','libx264','-crf','16','-preset','veryfast',out],check=True)
    else:
        a,b=s[1]
        subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{a:.3f}','-t',f'{b-a:.3f}','-i',R+'screen.mp4','-vf',f'tpad=stop_mode=clone:stop_duration={s[3]}','-r','30','-c:v','libx264','-crf','16','-preset','veryfast','-pix_fmt','yuv420p',out],check=True)
    parts.append(out)
open('parts.txt','w').write(''.join(f"file '{p}'\n" for p in parts))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i','parts.txt','-c','copy','video.mp4'],check=True)
# audio mix
ins=[];flt=[]
for k in range(1,8):
    ins+=['-i',f'{A}s{k}.{EXT}'];d=int(aud[k]*1000);flt.append(f'[{k-1}:a]aresample=48000,adelay={d}|{d}[a{k}]')
flt.append(''.join(f'[a{k}]' for k in range(1,8))+f'amix=inputs=7:normalize=0,apad,atrim=0:{total:.3f},loudnorm=I=-16:TP=-1.5[out]')
subprocess.run(['ffmpeg','-v','error','-y',*ins,'-filter_complex',';'.join(flt),'-map','[out]','-ac','2','-c:a','pcm_s16le','audio.wav'],check=True)
# captions from narration.md
rows=[l for l in open('/mnt/project-files/naacl-video/narration.md') if re.match(r'\|\s*\d\s*\|',l)]
text={int(r.split('|')[1]):r.split('|')[4].strip() for r in rows}
def chunks(t):
    out=[]
    for sent in re.split(r'(?<=[.?!])\s+',t):
        while len(sent)>84:
            cut=max(sent.rfind(', ',0,84),sent.rfind(': ',0,84))
            if cut<30: cut=sent.rfind(' ',0,80)
            out.append(sent[:cut+1].strip());sent=sent[cut+1:].strip()
        out.append(sent)
    return out
ts=lambda x:f'{int(x//3600):02}:{int(x%3600//60):02}:{int(x%60):02},{int(x*1000%1000):03}'
srt=[];n=1
for k in range(1,8):
    cs=chunks(text[k]);d=dur(f'{A}s{k}.{EXT}');tot=sum(len(c) for c in cs);t=aud[k]
    for c in cs:
        e=t+d*len(c)/tot;srt.append(f'{n}\n{ts(t)} --> {ts(e-0.05)}\n{c}\n');n+=1;t=e
open('captions.srt','w').write('\n'.join(srt))
style="FontName=Inter,FontSize=13,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,OutlineColour=&H80000000,BorderStyle=3,Outline=6,Shadow=0,MarginV=14"
subprocess.run(['ffmpeg','-v','error','-y','-i','video.mp4','-i','audio.wav','-vf',f"subtitles=captions.srt:force_style='{style}'",'-c:v','libx264','-crf','20','-preset','medium','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart','-shortest','finbot-naacl2027-demo.mp4'],check=True)
print('done',dur('finbot-naacl2027-demo.mp4'))
