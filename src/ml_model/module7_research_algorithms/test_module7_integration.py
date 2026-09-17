from __future__ import annotations
from src.ml_model.module1_iac_parser.parser_manager import process_iac_file
from src.ml_model.module2_uir.uir_schema import build_uir
from src.ml_model.module2_uir.graph_builder import GraphBuilder
from src.ml_model.module4_multi_agent.drift_detection_agent import DriftDetectionAgent
from src.ml_model.module4_multi_agent.evidence_collection_agent import EvidenceCollectionAgent
from src.ml_model.module6_runtime_telemetry import ConfigState,TelemetryDatum,MockConfigProvider,MockCloudWatchProvider,RuntimeStateCollector,TelemetryIntentDriftAnalyzer
from .research_architecture import ResearchArchitecture
from pathlib import Path
def main():
 root=Path(__file__).resolve().parents[3]; uir=GraphBuilder().attach_graph(build_uir(process_iac_file(str(root/'src/ml_model/module1_iac_parser/sample_terraform.tf'))))
 states=[ConfigState(resource_id=r['id'],resource_type=r['type'],provider='AWS',configuration=dict(r['properties'])) for r in uir['resources']]; states[0]=ConfigState(resource_id=states[0].resource_id,resource_type=states[0].resource_type,provider='AWS',configuration={**states[0].configuration,'instance_type':'t3.large'})
 runtime=RuntimeStateCollector(MockConfigProvider(states),MockCloudWatchProvider([TelemetryDatum(resource_id=states[0].resource_id,resource_type=states[0].resource_type,metric_name='CPUUtilization',namespace='AWS/EC2',timestamp='2026-01-01T00:00:00Z',value=96)] )).collect(uir)
 drift=TelemetryIntentDriftAnalyzer().analyze(uir,runtime); observed={'resources':[{'id':x.resource_id,'properties':x.configuration} for x in runtime.resources]}; result=DriftDetectionAgent().run(uir=uir,observed_state=observed,runtime_assessments=drift); evidence=EvidenceCollectionAgent().run(agent_results=(result,),evidence_records=runtime.collection_evidence)
 a=ResearchArchitecture(); consensus=a.consensus.analyze((result,),evidence.metadata['evidence']); target=drift[0].resource_id; blast=a.blast_radius.assess(uir,target); proposal=a.gate.propose(resource_id=target,proposed_change={'action':'align desired configuration'},blast_radius=blast,consensus=consensus[0],confidence=drift[0].confidence,risk=.1,evidence_ids=consensus[0].evidence_ids); ranks=a.ranker.rank(({'option_id':'repair','security':.8,'reliability':.8,'cost':.5,'risk':.1,'blast':blast.blast_radius_score,'confidence':.9},{'option_id':'replace','security':.9,'reliability':.7,'cost':.2,'risk':.8,'blast':.8,'confidence':.8}))
 assert drift and consensus and proposal and len(ranks)==2
 print('MODULE 7 REAL PROJECT INTEGRATION TEST: PASSED')
if __name__=='__main__':main()
