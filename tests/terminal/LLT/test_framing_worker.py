# @test T-LLT-063
# @requirements LLR-TERM-VIDEO-013, LLR-TERM-VIDEO-014, LLR-TERM-VIDEO-015, LLR-TERM-VIDEO-016, LLR-TERM-VIDEO-017
# @environment portable
# @plan Supply fake LiteRT tensors and a controlled native-thumbnail mailbox/clock while executing PersonDetector and AutoFraming. Assert model input/output contracts, two inference threads, person confidence/clipping, lazy worker reuse, session reset, stale/slow result rejection and wide-view recovery with thirty-second retry after detector errors. No inference model, camera or media thread is started.
# @pass Only timely results from the current enabled revision reach the native crop target; failures remain wide and bounded, and shutdown disables framing and joins once.
import ctypes as C
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, call
from zmala_terminal.linux import auto_framing as framing
from tests.support.ssh_deployment import Clock


class FramingWorkerTests(unittest.TestCase):
    def test_detector_model_contract_and_person_filter(self):
        interpreter=Mock(); dtype=object()
        interpreter.get_input_details.return_value=[{'shape':(1,300,300,3),'dtype':dtype,'index':9}]
        interpreter.get_output_details.return_value=[{'index':i} for i in range(4)]
        interpreter.get_tensor.side_effect=[[[[-.2,.1,.8,1.2],[.1,.1,.8,.8],[.2,.2,.4,.4],[.7,.7,.2,.2]]],[[0,2,0,0]],[[.9,.99,.44,.99]],[4]]
        tensors=[]
        class Tensor:
            def __getitem__(self,index):
                self.assertion=index; return self
        def asarray(image,dtype):
            tensors.append((image.copy(),dtype)); return Tensor()
        runtime=SimpleNamespace(Interpreter=Mock(return_value=interpreter))
        np=SimpleNamespace(uint8=dtype,asarray=asarray)
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,{'numpy':np,'ai_edge_litert.interpreter':runtime}),patch.object(sys,'path',list(sys.path)):
            root=Path(directory); packages=root/'framing-runtime/lib/python3.13/site-packages'; packages.mkdir(parents=True)
            detector=framing.PersonDetector(root/'models/person.tflite')
            runtime.Interpreter.assert_called_once_with(model_path=str(root/'models/person.tflite'),num_threads=2)
            self.assertIn(str(packages),sys.path)
            boxes=detector.detect(bytes([50,100,150])*8,4,2)
            self.assertEqual(boxes,[(.1,0.,1.,.8)])
            self.assertEqual(tensors[0][0].size,(300,300)); self.assertIs(tensors[0][1],dtype)
            self.assertIsNone(interpreter.set_tensor.call_args.args[1].assertion)
            interpreter.invoke.assert_called_once()
            interpreter.get_input_details.return_value=[{'shape':(1,224,224,3),'dtype':dtype}]
            with self.assertRaisesRegex(ValueError,'model input'): framing.PersonDetector(root/'models/person.tflite')
            interpreter.get_input_details.return_value=[{'shape':(1,300,300,3),'dtype':dtype}]
            interpreter.get_output_details.return_value=[]
            with self.assertRaisesRegex(ValueError,'postprocessing'): framing.PersonDetector(root/'models/person.tflite')

    def test_enable_is_boolean_lazy_and_worker_is_reused(self):
        plugin=Mock(); f=framing.AutoFraming(plugin,Path('assets'))
        with patch.object(framing.threading,'Thread') as thread:
            f.configure(1); thread.assert_not_called()
            f.configure(True); f.configure(True); thread.assert_called_once()
            self.assertEqual(thread.call_args.kwargs['name'],'person-framing')
            f.configure(False); f.configure(True); self.assertEqual(thread.call_count,1)
            f.close()
            thread.return_value.join.assert_called_once_with(timeout=4)
        self.assertTrue(f.closed.is_set()); self.assertEqual(f.status,'disabled')
        self.assertEqual(plugin.zmala_framing_enable.call_args_list,[call(1),call(0),call(1),call(0)])

    def worker(self,steps):
        plugin=Mock(); f=framing.AutoFraming(plugin,Path('assets')); f.enabled=True
        clock=Clock(); current={}; detector=Mock()
        steps=iter(steps)
        def wait(delay):
            item=next(steps,None)
            if item is None:
                f.closed.set(); f.enabled=False; return
            current.clear(); current.update(item); clock.now=item['time']
        f.changed=Mock(); f.changed.wait.side_effect=wait
        def take(buffer,width,height):
            C.cast(width,C.POINTER(C.c_int))[0]=2; C.cast(height,C.POINTER(C.c_int))[0]=2
            return current.get('token',1<<32|1)
        plugin.zmala_framing_take.side_effect=take
        def detect(rgb,width,height):
            self.assertEqual((len(rgb),width,height),(12,2,2))
            clock.now+=current.get('elapsed',.1)
            if current.get('disable'): f.configure(False)
            if current.get('change'): f.revision+=1
            if current.get('error'): raise RuntimeError('inference failed')
            return [(.4,.3,.6,.6)]
        detector.detect.side_effect=detect
        with patch.object(framing,'PersonDetector',return_value=detector) as construct, \
                patch.object(framing,'time',clock),patch.object(framing.os,'setpriority',side_effect=OSError(),create=True), \
                patch.object(framing.os,'PRIO_PROCESS',0,create=True):
            f._run()
        return f,plugin,detector,construct

    def test_only_current_timely_results_apply_and_new_session_starts_wide(self):
        f,p,d,construct=self.worker([{'time':0,'token':0},{'time':1},{'time':3},{'time':5,'elapsed':3.1},
                                    {'time':10,'change':True},{'time':12,'token':2<<32|1}])
        targets=p.zmala_framing_target.call_args_list
        self.assertEqual(len(targets),3)
        self.assertEqual(targets[0].args[1:],framing.WIDE)
        self.assertEqual(targets[1].args[-1],.5)
        self.assertEqual(targets[2].args,(2<<32|1,*framing.WIDE))
        construct.assert_called_once(); self.assertEqual(d.detect.call_count,5)
        _,p,_,_=self.worker([{'time':0,'disable':True}]); p.zmala_framing_target.assert_not_called()

    def test_failure_returns_wide_and_suppresses_retries_for_thirty_seconds(self):
        with self.assertLogs(level='ERROR'):
            f,p,d,_=self.worker([{'time':0,'error':True},{'time':5},{'time':29},{'time':31}])
        self.assertEqual(d.detect.call_count,2); self.assertEqual(p.zmala_framing_take.call_count,2)
        self.assertEqual(p.zmala_framing_target.call_args_list[0].args[1:],framing.WIDE)
        self.assertEqual(f.status,'active')
