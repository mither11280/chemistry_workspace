/* Offline, editable assignment-condition suggestions. Uses primary chapters. */
function parseAssignmentDescription(text, teaching=false, currentCourse='AS') {
  const lower=text.toLowerCase();
  const course=/paper\s*4|\ba2\b/i.test(text)?'A2':/paper\s*[12]|\bas\b/i.test(text)?'AS':currentCourse;
  if(teaching&&course==='A2')return parseA2Description(text);

  const legacy={atomic:['原子','电离能','ionisation','atomic'],stoich:['物质的量','摩尔','stoichiometry'],bonding:['化学键','bonding'],states:['物质状态','states'],energetics:['能量','焓','energetics'],electro:['氧化还原','redox'],equilibrium:['平衡','equilibrium'],kinetics:['速率','动力学','kinetics'],periodic:['无机','周期','periodic'],organic:['有机','organic'],analysis:['分析','光谱','analysis']};
  const chapters={
    ch01:['原子','atomic','同位素','isotop','电离能','ionisation','ionization'],
    ch02:['计量','摩尔','物质的量','stoichiometry'],
    ch03:['化学键','bonding','分子间作用力','氢键','intermolecular','hydrogen bond'],
    ch04:['物态','物质状态','理想气体','states of matter','ideal gas'],
    ch05:['焓','能量','energetics','enthalpy'],ch06:['氧化还原','redox'],
    ch07:['平衡','equilibr'],ch08:['速率','动力学','kinetics'],
    ch09:['周期','periodicity','periodic table'],ch10:['第2族','第 2 族','group 2'],
    ch11:['第17族','第 17 族','group 17','卤素'],ch12:['氮','硫','无机鉴定','nitrogen','sulfur','inorganic tests'],
    ch13:['有机入门','有机基础','异构','手性','命名','isomer','chiral','enantiom','nomenclature','hybridisation','hybridization'],
    ch14:['烃','聚合','hydrocarbon','polymer','alkene','alkane'],
    ch15:['卤代','halogen compounds','halogenoalkane'],ch16:['羟基','醇','hydroxy','alcohol'],
    ch17:['羧酸','腈','酯','carboxylic','nitrile','ester'],
    ch18:['羰基','醛','酮','官能团检验','carbonyl','aldehyde','ketone','functional group test'],
    ch19:['红外','质谱','分析技术','analytical','mass spect','infrared','infra-red','fragmentation']
  };
  const aliases=teaching?chapters:legacy;
  let topics=Object.keys(aliases).filter(id=>aliases[id].some(t=>lower.includes(t)));
  if(teaching){
    const explicit=[...lower.matchAll(/第\s*(\d{1,2})\s*章|chapter\s*(\d{1,2})/g)]
      .map(m=>+(m[1]||m[2])).filter(n=>n>=1&&n<=19).map(n=>'ch'+String(n).padStart(2,'0'));
    if(explicit.length)topics=[...new Set(explicit)];
    else if(/红外|infra[\s-]?red|\bir\b/.test(lower))topics=['ch19'];
    else if(/质谱|mass\s*spect|fragmentation|\bm\s*\+\s*1\b/.test(lower)){
      const advanced=/fragment|碎片|裂解|\bm\s*\+\s*1\b/.test(lower);
      const atomic=/relative atomic mass|相对原子质量|同位素|isotop|\bar\b/.test(lower);
      topics=[advanced||!atomic?'ch19':'ch01'];
    }
  }
  const match=text.match(/(\d+)\s*(?:道|题|个\s*小问|小问|questions?|items?)/i);
  return {topics,count:match?Math.min(200,Math.max(1,+match[1])):10,
    paper:/paper\s*2|结构题|大题|小问/i.test(text)?2:/paper\s*1|选择题/i.test(text)?1:0,
    year:(text.match(/20\d{2}/)||[])[0]||'',...(teaching?{course:'AS'}:{})};
}
function parseA2Description(text){
  // Teachers may type the subscript as ordinary text, with a space or in TeX.
  const lower=text.toLowerCase().replace(/\bk\s*(?:_\s*\{?\s*)?stab\s*\}?/g,'kstab'),aliases={
    'a2-ch01':['chemical energetics','group 2','第2族','化学能量','lattice','hydration','solution enthalpy','born','晶格','水合','溶解焓'],
    'a2-ch02':['entropy','gibbs','feasib','熵','吉布斯','自由能','可行性'],
    'a2-ch03':['electrochem','electrode','nernst','electrolysis','电化学','电极','电解'],
    'a2-ch04':['equilibr','buffer','pka','solubility product','partition','平衡','缓冲','溶度积','分配'],
    'a2-ch05':['kinetics','rate equation','reaction order','动力学','速率','反应级数'],
    'a2-ch06':['transition','complex','ligand','kstab','stability constant','稳定常数','过渡','配合物','配体'],
    'a2-ch07':['benzene','phenol','phenylamine','苯','苯酚','苯胺'],
    'a2-ch08':['acyl chloride','acid chloride','酰氯'],
    'a2-ch09':['amine','amide','胺','酰胺'],
    'a2-ch10':['polymer','聚合物','聚合'],
    'a2-ch11':['synthesis','multi-step','multistep','有机合成','多步合成','合成路线','stereoisomer','optical isomer','chiral','enantiom','racem','立体异构','手性','光学异构','外消旋','ozonolysis','臭氧化','diels','环加成'],
    'a2-ch12':['nmr','chromatograph','infrared','infra-red','mass spect','核磁','色谱','红外','质谱','分析技术']
  };
  let topics=Object.keys(aliases).filter(id=>aliases[id].some(t=>lower.includes(t)));
  if(/(?:aldehyde|ketone|carbonyl|醛|酮|羰基).{0,15}(?:reduc|还原)|(?:reduc|还原).{0,15}(?:aldehyde|ketone|carbonyl|醛|酮|羰基)/.test(lower)&&!topics.includes('a2-ch11'))topics.push('a2-ch11');
  // The teacher's organic stereochemistry rule does not move coordination
  // stereoisomers out of transition chemistry. Bare reagent names do not
  // establish which functional group is actually reduced.
  if(/complex|transition|配合物|过渡金属/.test(lower)&&
      /stereoisomer|optical isomer|chiral|立体异构|手性|光学异构|顺反异构/.test(lower)&&
      !/organic|有机|ozonolysis|臭氧化|diels|环加成/.test(lower))topics=topics.filter(t=>t!=='a2-ch11');
  if(/\b(?:ph|ka|kp|ksp)\b/.test(lower)&&!topics.includes('a2-ch04'))topics.push('a2-ch04');
  // A stability-constant equilibrium is taught with complexes. The generic
  // word "equilibrium" must not also pull ordinary chapter 4 questions in.
  if(/kstab|stability constant|稳定常数/.test(lower)&&
      !/\b(?:ph|ka|kp|ksp)\b|buffer|pka|solubility product|partition|缓冲|溶度积|分配/.test(lower)){
    topics=topics.filter(t=>t!=='a2-ch04');
  }
  topics.sort();
  if(/phenylamine|苯胺/.test(lower)&&!/aliphatic|alkylamine|amide|脂肪胺|烷基胺|酰胺/.test(lower))topics=topics.filter(t=>t!=='a2-ch09');
  const explicit=[...lower.matchAll(/第\s*(\d{1,2})\s*章|chapter\s*(\d{1,2})/g)].map(m=>+(m[1]||m[2]));
  if(explicit.some(n=>n<1||n>12))throw Error('A2 章节范围为 1–12');
  if(explicit.length)topics=[...new Set(explicit.map(n=>'a2-ch'+String(n).padStart(2,'0')))];
  const match=text.match(/(\d+)\s*(?:道|题|个\s*小问|小问|questions?|items?)/i);
  return {topics,count:match?Math.min(200,Math.max(1,+match[1])):10,paper:4,year:(text.match(/20\d{2}/)||[])[0]||'',course:'A2'};
}
if(typeof module!=='undefined')module.exports={parseAssignmentDescription};
