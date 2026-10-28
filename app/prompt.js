/* Offline, editable assignment-condition suggestions. Uses primary chapters. */
function parseAssignmentDescription(text, teaching=false) {
  const lower=text.toLowerCase();
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
    ch13:['有机入门','有机基础','异构','命名','isomer','nomenclature','hybridisation','hybridization'],
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
    year:(text.match(/20\d{2}/)||[])[0]||''};
}
if(typeof module!=='undefined')module.exports={parseAssignmentDescription};
