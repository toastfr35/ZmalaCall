# @test T-LLT-034
# @requirements TLLR006, TLLR008, TLLR009, TLLR035, TLLR039, TLLR040, TLLR041, TLLR042, TLLR043, TLLR044, TLLR079
# @environment portable
# @plan Drive model call states, availability changes, configuration validation, localization and carousel geometry with deterministic inputs; assert two-step calling, caller permission checks, cancellation, stable selection and three/five-contact layout.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.model import TerminalModel, State
from zmala_terminal.common.configuration import validate
from zmala_terminal.common.localization import LANGUAGES, translate
from zmala_terminal.common.carousel import CarouselMotion, CarouselLayout, carousel_contacts


def config():
    return {'schema_version': 1, 'configuration_version': 1, 'device_id': 'test',
            'call_auth_key': 'a-long-test-device-secret',
            'display_name': 'Family', 'auto_answer_seconds': 5,
            'sip': {'username': 'terminal', 'password': 'secret', 'domain': 'family.test', 'proxy': 'sip:family.test'},
            'contacts': [{'id': 'alice', 'name': 'Alice', 'sip_uri': 'sip:alice@family.test',
                          'can_call': True, 'can_receive': True, 'auto_answer': True, 'online': True}]}


class BehaviourTests(unittest.TestCase):
    def model(self):
        m = TerminalModel()
        m.configure(config())
        return m

    def test_red_cancels_auto_answer_and_late_connected_event(self):
        m = self.model()
        self.assertTrue(m.incoming('alice', 'family.test'))
        deadline = m.deadline
        self.assertEqual(m.button('red'), 'decline')
        self.assertIsNone(m.tick(deadline + 100))
        m.connected()
        self.assertEqual(m.state, State.STOPPING)
        m.ended()
        self.assertEqual(m.state, State.HOME)

    def test_unknown_domain_caller_and_disabled_direction_are_rejected(self):
        m = self.model()
        self.assertFalse(m.incoming('unknown', 'family.test'))
        self.assertFalse(m.incoming('alice', 'untrusted.test'))
        c = config()
        c['contacts'][0].update(can_receive=False, auto_answer=False)
        m.configure(c)
        self.assertFalse(m.incoming('alice', 'family.test'))
        self.assertIsNone(m.button('green'))
        self.assertEqual(m.state, State.CONFIRMING)
        self.assertEqual(m.button('green'), 'dial')

    def test_buttons_are_inert_during_call_and_auto_answer_is_once(self):
        m = self.model()
        m.incoming('alice', 'family.test')
        self.assertEqual(m.tick(m.deadline + 1), 'answer')
        self.assertIsNone(m.tick())
        m.connected()
        for button in ['left', 'right', 'green']:
            self.assertIsNone(m.button(button))
        self.assertEqual(m.button('red'), 'end')

    def test_offline_cannot_dial_and_config_preserves_selected_person(self):
        m = self.model()
        self.assertIsNone(m.button('green', registered=False))
        c = config()
        c['contacts'].insert(0, dict(c['contacts'][0], id='bob', name='Bob', sip_uri='sip:bob@family.test'))
        m.configure(c)
        self.assertEqual(m.selected['id'], 'alice')

    def test_malformed_configuration_is_rejected(self):
        c = config()
        self.assertEqual(validate(c, 'test'), c)
        for mutation in [lambda c: c.update(device_id='other'),
                         lambda c: c.update(command_shell='unsupported'),
                         lambda c: c['contacts'][0].update(online='yes'),
                         lambda c: c.update(auto_answer_seconds=0),
                         lambda c: c['contacts'][0].update(sip_uri='sip:attacker@elsewhere'),
                         lambda c: c['contacts'][0].update(can_receive=False)]:
            bad = copy.deepcopy(c)
            mutation(bad)
            with self.assertRaises(ValueError):
                validate(bad, 'test')

    def test_offline_and_unknown_contacts_offer_callbacks_without_dialing(self):
        m = self.model()
        m.config['contacts'][0]['online'] = False
        self.assertIsNone(m.button('green'))
        self.assertEqual(m.state, State.CONFIRM_CALLBACK)
        self.assertEqual(m.button('green'), 'request_callback')
        self.assertEqual(m.state, State.REQUESTING_CALLBACK)
        self.assertIsNone(m.button('green'), 'Repeated green must not duplicate the request')
        m.ended()
        del m.config['contacts'][0]['online']
        self.assertIsNone(m.button('green'))
        self.assertEqual(m.state, State.CONFIRM_CALLBACK)
        m.button('right')
        self.assertEqual(m.state, State.HOME)
        m.config['contacts'][0]['online'] = True
        self.assertIsNone(m.button('green'))
        self.assertEqual(m.state, State.CONFIRMING)
        self.assertEqual(m.button('green'), 'dial')

    def test_confirmation_cancels_on_every_other_button_without_changing_selection(self):
        for button in ['left', 'right', 'red', 'cancel']:
            m = self.model()
            m.config['contacts'].append(dict(m.selected, id='bob', name='Bob'))
            self.assertIsNone(m.button('green'))
            self.assertEqual(m.state, State.CONFIRMING)
            self.assertIsNone(m.tick(1e12), 'Confirmation must never auto-dial')
            self.assertIsNone(m.button(button))
            self.assertEqual(m.state, State.HOME)
            self.assertEqual(m.selected['id'], 'alice')
            self.assertIsNone(m.contact)

    def test_confirmation_accepts_incoming_calls_and_cannot_dial_without_registration(self):
        m = self.model()
        m.button('green')
        self.assertIsNone(m.button('green', registered=False))
        self.assertEqual(m.state, State.CONFIRMING)
        self.assertTrue(m.incoming('alice', 'family.test'))
        self.assertEqual(m.state, State.RINGING)

    def test_account_auto_answer_overrides_contact_flags_and_still_requires_permission(self):
        c = config()
        c['auto_answer'] = False
        m = TerminalModel()
        m.configure(c)
        self.assertTrue(m.incoming('alice', 'family.test'))
        self.assertIsNone(m.deadline)
        m.ended()
        c['auto_answer'] = True
        c['contacts'][0]['auto_answer'] = False
        c['contacts'].append(dict(c['contacts'][0], id='bob', name='Bob', sip_uri='sip:bob@family.test'))
        m.configure(c)
        for caller in ['alice', 'bob']:
            self.assertTrue(m.incoming(caller, 'family.test'))
            self.assertIsNotNone(m.deadline)
            self.assertEqual(m.tick(m.deadline + 1), 'answer')
            m.ended()
        c['contacts'][1]['can_receive'] = False
        self.assertFalse(m.incoming('bob', 'family.test'))
        c['auto_answer'] = 'yes'
        with self.assertRaises(ValueError):
            validate(c, 'test')

    def test_carousel_keeps_selected_person_in_center_and_wraps_without_duplicate_slots(self):
        m = TerminalModel()
        self.assertEqual(m.carousel, [None, None, None])
        c = config()
        m.configure(c)
        self.assertEqual([p['id'] if p else None for p in m.carousel], [None, 'alice', None])
        c['contacts'].append(dict(c['contacts'][0], id='bob', name='Bob', sip_uri='sip:bob@family.test'))
        m.configure(c)
        self.assertEqual([p['id'] if p else None for p in m.carousel], [None, 'alice', 'bob'])
        c['contacts'].append(dict(c['contacts'][0], id='carol', name='Carol', sip_uri='sip:carol@family.test'))
        c['contacts'].append(dict(c['contacts'][0], id='blocked', name='Blocked', can_call=False))
        m.configure(c)
        self.assertEqual([p['id'] for p in m.carousel], ['carol', 'alice', 'bob'])
        m.button('right')
        self.assertEqual([p['id'] for p in m.carousel], ['alice', 'bob', 'carol'])
        m.button('left')
        m.button('left')
        self.assertEqual([p['id'] for p in m.carousel], ['bob', 'carol', 'alice'])

    def test_languages_are_complete_and_countdowns_format_without_fallback(self):
        c = config()
        for code, language in LANGUAGES.items():
            c['language'] = code
            self.assertEqual(validate(c, 'test')['language'], code)
            self.assertEqual(set(language['messages']), set(LANGUAGES['en']['messages']))
            self.assertTrue(all(language['messages'].values()))
            self.assertIn('7', translate(code, 'countdown', seconds=7))
            self.assertIn('Noah', translate(code, 'call_question', name='Noah'))
        for invalid in ['unknown', '', None, 3]:
            c['language'] = invalid
            with self.assertRaises(ValueError):
                validate(c, 'test')

    def test_carousel_motion_wraps_and_is_independent_of_frame_rate(self):
        people = [{'id': str(i)} for i in range(5)]
        for index, direction in [(4, 1), (0, -1)]:
            motion = CarouselMotion(people, index, direction, 10)
            start = next(person for person, slot in motion.frames(10) if slot == 0)
            finish = next(person for person, slot in motion.frames(11) if slot == 0)
            self.assertEqual(start, people[index])
            self.assertEqual(finish, people[(index+direction)%5])
            positions = [next(slot for person, slot in motion.frames(t) if person == start) for t in [10,10.05,10.15,10.28]]
            self.assertTrue(all(a>=b if direction>0 else a<=b for a,b in zip(positions, positions[1:])))
            self.assertEqual(motion.progress(9), 0)
            self.assertEqual(motion.progress(11), 1)
        two = CarouselMotion(people[:2], 0, 1, 0)
        self.assertEqual([p['id'] for p,slot in two.frames(.14) if p], ['0','1'])

    def test_animation_deadlines_absorb_draw_time_and_skip_missed_frames(self):
        motion = CarouselMotion([], 0, 1, 0)
        self.assertEqual(motion.next_frame_delay(.004), 13)
        self.assertEqual(motion.next_frame_delay(.045), 5)
        # Four milliseconds of rendering must not accumulate each frame.
        now = 0
        for _ in range(30):
            now += .004
            now += motion.next_frame_delay(now)/1000
        self.assertAlmostEqual(now, .5, delta=.001)
        self.assertGreaterEqual(motion.next_frame_delay(1/60), 1)

    def test_carousel_configuration_validation(self):
        for value in (3, 5):
            self.assertEqual(validate(config() | {'carousel_portraits': value}, 'test')['carousel_portraits'], value)
        for value in (True, None, 3.0, '5', 4, 0, [], {}):
            with self.assertRaises(ValueError):
                validate(config() | {'carousel_portraits': value}, 'test')
        validate(config(), 'test')

    def test_wide_carousel_fits_five_unique_contacts_and_larger_focus(self):
        people = [{'id': str(i)} for i in range(7)]
        wide = CarouselLayout.fit(1840, 800, len(people), 5)
        small = CarouselLayout.fit(820, 350, len(people))
        self.assertEqual(wide.slots, 5)
        self.assertEqual(small.slots, 3)
        self.assertGreater(wide.portrait_size, small.portrait_size)
        self.assertEqual(CarouselLayout.fit(1840, 800, 4, 5).slots, 3)
        self.assertEqual(CarouselLayout.fit(1840, 800, 7).slots, 3)
        self.assertEqual(CarouselLayout.fit(1240, 450, 7, 5).slots, 5)
        self.assertEqual(CarouselLayout.fit(1840, 800, 7, 3).slots, 3)
        for index in range(len(people)):
            visible = carousel_contacts(people, index, 5)
            self.assertEqual(visible[2], people[index])
            self.assertEqual(len({p['id'] for p in visible}), 5)
            for direction in (-1, 1):
                motion = CarouselMotion(people, index, direction, 0)
                end = {round(slot): person for person, slot in motion.frames(1, 5) if abs(slot) <= 2}
                self.assertEqual([end[slot] for slot in range(-2, 3)],
                                 carousel_contacts(people, index+direction, 5))
        # Outer cards leave space for the arrows, even at the width breakpoint.
        for width in (700, 820, 1240, 1400, 1840, 3760):
            layout = CarouselLayout.fit(width, 450, 7, 5)
            self.assertGreater(width/2-layout.offset(2)-layout.portrait_size*.25-14, 50)
            center_gap = layout.offset(1)-layout.portrait_size*.75-26
            side_gap = layout.offset(2)-layout.offset(1)-layout.portrait_size*.5-24
            self.assertGreaterEqual(center_gap, 12)
            self.assertAlmostEqual(center_gap, side_gap, delta=2.01)


if __name__ == '__main__':
    unittest.main()
