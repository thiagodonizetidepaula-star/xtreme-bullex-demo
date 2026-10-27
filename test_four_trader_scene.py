"""Visual-only regression for the four-trader central dealing room."""
from pathlib import Path
import unittest

HTML=(Path(__file__).resolve().parent/'templates'/'office.html').read_text(encoding='utf-8')

class FourTraderRoomTests(unittest.TestCase):
    def test_exactly_four_visual_workstations(self):
        scene=HTML.split('const fourTraderRoom=true;',1)[1].split("$('avatarTest').onclick=",1)[0]
        self.assertIn('const workstationPositions=[',scene)
        self.assertIn('for(let i=0;i<4;i++){',scene)
        self.assertIn('const person=team[i];',scene)
        self.assertIn("person.role='desk'",scene)
        self.assertIn("for(const p of team.slice(4))p.group.visible=false;",scene)
        self.assertIn('person.group.rotation.y=i<2?0:Math.PI;',scene)

    def test_oversized_dual_monitors_preserve_existing_data_binding(self):
        scene=HTML.split('const fourTraderRoom=true;',1)[1]
        self.assertIn("for(const mx of [-.63,.63])",scene)
        self.assertIn("screenTargets.push(plane)",scene)
        self.assertIn("charts.push({ctx,tex,seed:i",scene)
        self.assertIn("bigTV('OPERAÇÕES DEMO'",scene)
        self.assertIn("bigTV('LABORATÓRIO'",scene)
        self.assertIn("bigTV('MURAL DOS TRADERS'",scene)

    def test_only_old_visual_world_is_hidden_not_backend(self):
        scene=HTML.split('const fourTraderRoom=true;',1)[1]
        self.assertIn('const previousVisuals=scene.children.slice();',scene)
        self.assertIn('if(!object.isLight&&!activeTigerStaff.includes(object))object.visible=false;',scene)
        self.assertIn('const activeTigerStaff=team.slice(0,4)',scene)
        self.assertIn('if(fourTraderRoom)return;',HTML)
        self.assertIn('if(fourTraderRoom&&i>=4)continue;',HTML)

if __name__=='__main__':unittest.main()
