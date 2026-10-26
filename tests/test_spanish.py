#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spanish's own checks and card parts (pipeline/spanish.py). No Anki, no network.

    python3 tests/test_spanish.py

The word line, the value order of the patterns, the anchoring of a pattern in conjugated sentences, the leak
check, the variety that follows the voice, the noun's article in the cloze blank, the placeholders a pattern may
add to the headword, and the translation languages of a Spanish learner. The golden cards
(tests/golden/cards/es/) show the same pieces on whole cards.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios as cs  # noqa: E402  (stubs aqt and puts the add-on on the path)
from pipeline import languages  # noqa: E402
from pipeline import spanish as S  # noqa: E402

generate, prompts, providers = cs.generate, cs.prompts, cs.providers


def noun(article, gender, singular, plural):
    return {"pos": "noun", "article": article, "gender": gender, "noun": singular, "plural": plural}


def verb(infinitive, yo, preterite, participle):
    return {"pos": "verb", "infinitive": infinitive, "yo": yo, "preterite": preterite, "participle": participle}


def line(*bits):
    return '<div class="morph">%s</div>' % " · ".join(bits)


EL, LA = '<span class="g-der">el</span>', '<span class="g-die">la</span>'


class WordLine(unittest.TestCase):
    """The article in its gender's colour on every noun, the plural only when it is not simply -s or -es, the
    four verb forms only for an irregular or stem-changing verb."""

    def test_the_article_shows_the_gender(self):
        self.assertEqual(S.morphology_html(noun("la", "f", "mesa", "las mesas")), line(LA))
        self.assertEqual(S.morphology_html(noun("el", "m", "libro", "los libros")), line(EL))
        self.assertEqual(S.morphology_html(noun("el", "m", "problema", "los problemas")), line(EL))    # -a, masculine
        self.assertEqual(S.morphology_html(noun("la", "f", "mano", "las manos")), line(LA))            # -o, feminine
        self.assertEqual(S.morphology_html(noun("el", "m", "papel", "los papeles")), line(EL))
        self.assertEqual(S.morphology_html(noun("el", "m", "sofá", "los sofás")), line(EL))

    def test_plurals_worth_learning(self):
        self.assertEqual(S.morphology_html(noun("la", "f", "canción", "las canciones")), line(LA, "Pl. las canciones"))
        self.assertEqual(S.morphology_html(noun("el", "m", "examen", "los exámenes")), line(EL, "Pl. los exámenes"))
        self.assertEqual(S.morphology_html(noun("la", "f", "crisis", "las crisis")), line(LA, "Pl. las crisis"))
        self.assertEqual(S.morphology_html(noun("el", "m", "lunes", "los lunes")), line(EL, "Pl. los lunes"))
        self.assertEqual(S.morphology_html(noun("la", "f", "luz", "las luces")), line(LA, "Pl. las luces"))

    def test_a_feminine_noun_with_el(self):
        self.assertEqual(S.morphology_html(noun("el", "f", "agua", "las aguas")), line(LA.replace(">la<", ">el<"),
                                                                                      "Pl. las aguas"))

    def test_a_wrong_z_plural_is_repaired(self):
        self.assertEqual(S.morphology_html(noun("el", "m", "lápiz", "los lápizes")), line(EL, "Pl. los lápices"))
        self.assertEqual(S.morphology_html(noun("la", "f", "voz", "las vozes")), line(LA, "Pl. las voces"))

    def test_regular_verbs_show_nothing(self):
        for m in (verb("hablar", "hablo", "habló", "hablado"), verb("vivir", "vivo", "vivió", "vivido"),
                  verb("comer", "como", "comió", "comido"), verb("buscar", "busco", "buscó", "buscado"),
                  verb("levantarse", "me levanto", "se levantó", "levantado"), {"pos": "other"}, None, "garbage",
                  noun("", "f", "mesa", "las mesas")):
            self.assertEqual(S.morphology_html(m), "", m)

    def test_irregular_and_stem_changing_verbs(self):
        self.assertEqual(S.morphology_html(verb("tener", "tengo", "tuvo", "tenido")),
                         line("tener", "yo tengo", "él tuvo", "tenido"))
        self.assertEqual(S.morphology_html(verb("ir", "voy", "fue", "ido")), line("ir", "yo voy", "él fue", "ido"))
        self.assertEqual(S.morphology_html(verb("pensar", "pienso", "pensó", "pensado")),
                         line("pensar", "yo pienso", "él pensó", "pensado"))
        self.assertEqual(S.morphology_html(verb("pedir", "pido", "pidió", "pedido")),
                         line("pedir", "yo pido", "él pidió", "pedido"))
        self.assertEqual(S.morphology_html(verb("volver", "vuelvo", "volvió", "vuelto")),
                         line("volver", "yo vuelvo", "él volvió", "vuelto"))
        self.assertEqual(S.morphology_html(verb("conocer", "conozco", "conoció", "conocido")),
                         line("conocer", "yo conozco", "él conoció", "conocido"))
        self.assertEqual(S.morphology_html(verb("acordarse", "me acuerdo", "se acordó", "acordado")),
                         line("acordarse", "me acuerdo", "se acordó", "acordado"))

    def test_a_regularized_form_is_replaced_from_the_table(self):
        self.assertEqual(S.morphology_html(verb("tener", "teno", "tení", "tenido")),
                         line("tener", "yo tengo", "él tuvo", "tenido"))
        self.assertEqual(S.morphology_html(verb("hacer", "hago", "hací", "hacido")),
                         line("hacer", "yo hago", "él hizo", "hecho"))
        self.assertEqual(S.morphology_html(verb("abrir", "abro", "abrió", "abrido")),
                         line("abrir", "yo abro", "él abrió", "abierto"))

    def test_the_line_is_escaped(self):
        self.assertNotIn("<b>", S.morphology_html(noun("el", "m", "<b>x</b>", "los <b>xes</b>")))
        self.assertNotIn("<b>", S.morphology_html(verb("<b>ir</b>", "<b>voy</b>", "<b>fue</b>", "<b>ido</b>")))


class PatternOrder(unittest.TestCase):
    RANKS = [
        ("pensar en algo", 1), ("darse cuenta de algo", 1), ("gracias por algo", 1), ("estudiar para algo", 1),
        ("establecer contacto con alguien", 1), ("tomar el pelo a alguien", 1),
        ("harto de algo", 2), ("el plazo de algo", 2), ("por la mañana", 2), ("dentro del plazo", 2),
        ("después de algo", 2), ("antes de + infinitivo", 2), ("estar cansado de + infinitivo", 2),
        ("ser capaz de + infinitivo", 2), ("estar de acuerdo con alguien", 2), ("este fin de semana", 2),
        ("tener que + infinitivo", 3), ("ir a + infinitivo", 3), ("seguir + gerundio", 3), ("estar + gerundio", 3),
        ("haber + participio", 3), ("es importante que + subjuntivo", 3), ("antes de que + subjuntivo", 3),
        ("estar de acuerdo", 4), ("me gusta + infinitivo", 4), ("le duele algo", 4), ("estar + adjetivo", 4),
        ("tomar una decisión", 5), ("esta noche", 5),
        ("decir que", 6), ("Le informo que + cláusula", 6),
        ("llevar + sustantivo + por si acaso + verbo", 9),         # the sentence's skeleton, last
        # dropped: a bare object, a preposition alone (the live run had "aprovechar + sustantivo", "tener + sustantivo")
        ("comprar algo", None), ("en algo", None), ("aprovechar + sustantivo", None), ("tener + sustantivo", None),
    ]

    def test_ranks(self):
        for pattern, rank in self.RANKS:
            self.assertEqual(S.pattern_rank(pattern), rank, pattern)
        self.assertIsNone(S.pattern_rank(""))

    def test_estar_is_never_a_prefix(self):
        # "est" once made estudiar and establecer count as estar (rank 4)
        self.assertEqual(S.pattern_rank("estudiar para algo"), 1)
        self.assertEqual(S.pattern_rank("está cansado de algo"), 2)


class PatternAnchoring(unittest.TestCase):
    FOUND = [
        ("pensar en algo", "siempre pienso en ti cuando llueve."),            # e -> ie
        ("volver a + infinitivo", "vuelvo a llamarte mañana."),              # o -> ue
        ("pedir algo", "pidió un café."),                                     # e -> i
        ("dormir bien", "anoche durmió muy bien."),                           # o -> u
        ("jugar al fútbol", "juego al fútbol los sábados."),                  # u -> ue
        ("oler a algo", "la casa huele a café."),                             # o -> hue
        ("seguir + gerundio", "sigue lloviendo desde ayer."),                 # the silent u of gu
        ("conseguir algo", "consiguió el trabajo."),
        ("buscar un piso", "busqué un piso cerca del centro."),               # c -> qu
        ("llegar a algo", "llegué a casa muy tarde."),                        # g -> gu
        ("empezar a + infinitivo", "empecé a trabajar en mayo."),             # z -> c
        ("conocer a alguien", "conozco a tu hermano."),                       # c -> zc
        ("tener que + infinitivo", "ayer tuve que trabajar hasta tarde."),    # irregular
        ("ir a + infinitivo", "mañana vamos a comer juntos."),
        ("hacer la cena", "hoy hago yo la cena."),
        ("darse cuenta de algo", "no me di cuenta del error."),
        ("ser capaz de + infinitivo", "fue capaz de terminarlo."),
        ("saber + infinitivo", "supe la verdad ayer."),
        ("decir que", "dijo que vendría."),
        ("traer algo", "trajo pan."),
        ("oír algo", "¿oyes la música?"),
        ("oír algo", "no oigo nada."),
        ("reírse de algo", "se rio de mí."),
        ("estar de acuerdo con alguien", "estoy de acuerdo contigo."),
        ("me gusta + infinitivo", "me gusta mucho leer."),
        ("le duele algo", "a mi madre le duele la cabeza."),
        ("haber + participio", "¿ha pensado usted en nuestra propuesta?"),
        ("tomar el pelo a alguien", "¿me estás tomando el pelo?"),
        ("echar de menos a alguien", "te echo de menos."),
    ]

    def test_forms_of_the_words_count(self):
        for pattern, text in self.FOUND:
            self.assertTrue(S.pattern_in_text(pattern, text), (pattern, text))

    def test_invented_patterns_and_bare_labels_fail(self):
        self.assertFalse(S.pattern_in_text("acabar de + infinitivo", "siempre pienso en ti."))
        self.assertFalse(S.pattern_in_text("pretérito indefinido", "ayer comí paella."))
        self.assertFalse(S.pattern_in_text("ordenar algo", "pienso en ti."))

    def test_whole_words_only(self):
        self.assertFalse(S.pattern_in_text("estudiar para algo", "la parada del autobús está cerca."))
        self.assertFalse(S.pattern_in_text("para + infinitivo", "la parada del autobús está cerca."))

    def test_a_frame_must_be_there_in_order(self):
        # the live run kept "tener que + infinitivo" for "la cita que tiene": the model copies the prompt's examples
        self.assertFalse(S.pattern_in_text("tener que + infinitivo", "le recuerdo la cita que tiene mañana a las diez."))
        self.assertFalse(S.pattern_in_text("ir a + infinitivo", "voy a casa."))
        self.assertFalse(S.pattern_in_text("volver a + infinitivo", "vuelvo a casa."))
        for pattern, text in (("ir a + infinitivo", "lo vamos a hacer."), ("me gusta + infinitivo", "me gusta mucho leer."),
                              ("estar + gerundio", "¿me estás tomando el pelo?"),
                              ("haber + participio", "¿ha visto usted la película?"),
                              ("poder + infinitivo", "¿podría usted mover la mesa?"),
                              ("¿Puede usted + infinitivo?", "¿puede usted limpiar la mesa?"),
                              ("capaz de + infinitivo", "fue capaz de terminarlo."),
                              ("volver a + infinitivo", "vuelvo a llamarte mañana.")):
            self.assertTrue(S.pattern_in_text(pattern, text), (pattern, text))

    def test_accent_twins_never_count(self):
        # "dé" (dar) without its accent is "de": "darse cuenta de algo" was kept for "la reunión de mañana"
        self.assertFalse(S.pattern_in_text("darse cuenta de algo", "¿podría usted aprovechar la reunión de mañana?"))
        self.assertFalse(S.pattern_in_text("saber + infinitivo", "se fue a casa."))

    def test_ser_and_estar_by_their_whole_forms(self):
        self.assertFalse(S.pattern_in_text("estar de acuerdo con alguien", "estudio con mi amigo."))
        self.assertFalse(S.pattern_in_text("estar + gerundio", "esta casa es bonita y estudiando aprendo."))
        self.assertTrue(S.pattern_in_text("estar + gerundio", "está lloviendo."))
        self.assertTrue(S.pattern_in_text("ser capaz de + infinitivo", "es capaz de todo."))


class Leak(unittest.TestCase):
    def test_another_script_or_a_foreign_function_word(self):
        self.assertEqual(S.leak("Mañana tengo una cita con the médico."), "the")
        self.assertEqual(S.leak("Voy al مكتب mañana."), "م")
        self.assertEqual(S.leak("Привет, ¿qué tal?"), "П")
        self.assertEqual(S.leak("Wir gehen und hablamos."), "wir")
        self.assertEqual(S.leak("Je suis muy cansado."), "je")
        self.assertEqual(S.leak("Eu estou cansado."), "estou")
        self.assertEqual(S.leak("Ik ben moe."), "ik")
        self.assertEqual(S.leak("todo bien", "Non lo so."), "non")       # every text is checked

    def test_spanish_with_loanwords_names_and_shared_words_is_clean(self):
        for t in ("¿Me das un vaso de agua?", "He comido demasiado.", "¿Has visto la película?", "No, gracias.",
                  "Le doy el libro.", "Ve a casa.", "Con mucho gusto.", "Vamos al café.", "Hay wifi en el hotel.",
                  "Ellos van al cine y le dan un regalo.", "Este fin de semana descanso.", "Tengo un chat con mis amigos.",
                  "Me encanta el fútbol.", "La reunión es a las diez.", "Vengo de Los Ángeles.", "Tom es mi amigo.",
                  "Una pizza, por favor.", "Ayer fui al médico.", "Él tiene un hermano.", "No sé nada.",
                  "Si quieres, vamos.", "Es una buena idea.", "Pon la taza en la mesa.", "¡Ale, vamos!",
                  "Che, ¿venís mañana?", "Quiero que me des tu número."):
            self.assertIsNone(S.leak(t), t)


class VarietyFollowsTheVoice(unittest.TestCase):
    """Spain by default; a Latin American voice gives Latin American Spanish (like US or UK for English)."""

    def test_variety(self):
        spain = prompts.main_system("es", "B1", "Arabic", voice="es-ES-ElviraNeural")
        mexico = prompts.main_system("es", "B1", "Arabic", voice="es-MX-DaliaNeural")
        self.assertIn("the Spanish of Spain: vosotros for the casual plural", spain)
        self.assertIn("coche, ordenador, móvil, zumo, conducir", spain)
        self.assertIn("neutral Latin American Spanish as spoken in Mexico: ustedes for every plural, never vosotros", mexico)
        self.assertIn("carro, computadora, celular, jugo, manejar, chamarra for a jacket", mexico)
        # naming the vulgar word invited it in a live run, so no prompt names it
        self.assertNotIn("chaqueta", mexico)
        # the main user message ends with the country too: the cloze call, which had it there, wrote "chamarra"
        self.assertTrue(prompts.main_user("es", "ponerse", "Tarkib Spanish", voice="es-MX-DaliaNeural").endswith(
            " Use the Latin American Spanish of Mexico (ustedes, carro, computadora, chamarra), never vosotros."))
        for voice in ("es-ES-ElviraNeural", "es-PE-CamilaNeural", ""):
            self.assertNotIn("Latin American", prompts.main_user("es", "ponerse", "Tarkib Spanish", voice=voice), voice)
        for voice in ("es-AR-ElenaNeural", "es-CO-SalomeNeural", "es-US-PalomaNeural", "es-PE-CamilaNeural"):
            self.assertIn("never vosotros", prompts.main_system("es", "A2", "French", voice=voice), voice)
        self.assertIn("as spoken in Argentina", prompts.main_system("es", "B1", "French", voice="es-AR-ElenaNeural"))
        self.assertNotIn("chaqueta", prompts.main_system("es", "B1", "French", voice="es-CO-SalomeNeural"))
        # a Latin American voice Settings does not offer keeps the words used across Latin America
        self.assertIn("words used across Latin America (carro, computadora",
                      prompts.main_system("es", "B1", "French", voice="es-PE-CamilaNeural"))
        self.assertIn("SPELLING: Use the Spanish of Spain",
                      prompts.main_system("es", "Native", "Arabic", voice="es-ES-ElviraNeural"))
        self.assertIn("SPELLING: Use the Latin American Spanish of Mexico",
                      prompts.main_system("es", "Native", "Arabic", voice="es-MX-DaliaNeural"))
        self.assertIn("Use the Latin American Spanish of Mexico (ustedes, carro, computadora, chamarra), never vosotros.",
                      prompts.cloze_user("es", "x", "d", "m", "B1", "Arabic", "es-MX-DaliaNeural"))

    def test_a_mexican_voice_never_reads_chaqueta(self):
        # a live card: "¿Podría usted ponerse la chaqueta antes de la reunión?" with the Mexican voice
        mx = "es-MX-DaliaNeural"
        self.assertEqual(S.country_words("¿Podría usted ponerse la chaqueta antes de la reunión?", mx, "ponerse"),
                         "¿Podría usted ponerse la chamarra antes de la reunión?")
        self.assertEqual(S.country_words("Chaquetas nuevas y una chaqueta vieja.", mx, "comprar"),
                         "Chamarras nuevas y una chamarra vieja.")
        # the card teaches the word itself, another country, or a word that only contains it
        self.assertEqual(S.country_words("Me pongo la chaqueta.", mx, "la chaqueta"), "Me pongo la chaqueta.")
        for voice in ("es-ES-ElviraNeural", "es-CO-SalomeNeural", ""):
            self.assertEqual(S.country_words("Me pongo la chaqueta.", voice, "ponerse"), "Me pongo la chaqueta.")
        self.assertEqual(S.country_words("Una chaquetilla corta.", mx, "x"), "Una chaquetilla corta.")
        self.assertIs(generate.RULES["es"]["country_words"], S.country_words)

    def test_usted_is_one_person_in_arabic(self):
        # four of five Arabic formal sentences of the first live run used the plural (يمكنكم)
        rule = "Usted speaks to ONE person"
        self.assertIn(rule, prompts.main_system("es", "B1", "Arabic", voice="es-ES-ElviraNeural"))
        self.assertIn(rule, prompts.main_system("es", "Native", "Arabic", voice="es-MX-DaliaNeural"))
        self.assertNotIn(rule, prompts.main_system("es", "B1", "French", voice="es-ES-ElviraNeural"))
        self.assertNotIn(rule, prompts.main_system("en", "B1", "Arabic", voice="en-US-JennyNeural"))

    def test_the_default_voice_is_from_spain(self):
        self.assertEqual(languages.get("es")["default_voice"], "es-ES-ElviraNeural")
        self.assertEqual(languages.get("es")["voice_locales"][0], "es-ES")


class ClozeArticle(unittest.TestCase):
    """A noun's blank takes its article, so the gender is part of the answer."""

    def test_the_article_joins_the_noun(self):
        self.assertEqual(S.cloze_article("La mesa es nueva.", "mesa", "single_word", "la mesa"), "La mesa")
        self.assertEqual(S.cloze_article("La mesa es nueva.", "mesa", "single_word", "mesa"), "La mesa")   # typed bare
        self.assertEqual(S.cloze_article("¿La mesa es nueva?", "mesa", "single_word", "mesa"), "La mesa")
        self.assertEqual(S.cloze_article("El agua está muy fría.", "agua", "single_word", "el agua"), "El agua")
        self.assertEqual(S.cloze_article("Compré una mesa ayer.", "mesa", "single_word", "mesa"), "una mesa")

    def test_everything_else_stays(self):
        self.assertEqual(S.cloze_article("Mi hermana tiene dos hijos.", "tiene", "single_word", "tener"), "tiene")
        self.assertEqual(S.cloze_article("La casa es roja.", "roja", "single_word", "rojo"), "roja")
        self.assertEqual(S.cloze_article("Las mesas son nuevas.", "mesas", "single_word", "mesa"), "mesas")
        self.assertEqual(S.cloze_article("Tengo una cita a las diez.", "una cita", "single_word", "la cita"),
                         "una cita")
        self.assertEqual(S.cloze_article("Siempre pienso en ti.", "en", "verb_prep", "pensar en"), "en")


class Headword(unittest.TestCase):
    """The model often keeps a bare noun as typed; the card shows it with the word line's article."""

    def test_a_bare_noun_gets_its_article(self):
        self.assertEqual(S.headword("mesa", noun("la", "f", "mesa", "las mesas")), "la mesa")
        self.assertEqual(S.headword("agua", noun("el", "f", "agua", "las aguas")), "el agua")
        self.assertEqual(S.headword("cancion", noun("la", "f", "canción", "las canciones")), "la canción")

    def test_everything_else_stays(self):
        self.assertEqual(S.headword("la mesa", noun("la", "f", "mesa", "las mesas")), "la mesa")
        self.assertEqual(S.headword("tener", verb("tener", "tengo", "tuvo", "tenido")), "tener")
        self.assertEqual(S.headword("Madrid", noun("", "m", "Madrid", "")), "Madrid")
        self.assertEqual(S.headword("mesa", {"pos": "other"}), "mesa")
        self.assertEqual(S.headword("mesa", None), "mesa")
        self.assertEqual(S.headword("mesa", noun("la", "f", "silla", "las sillas")), "mesa")      # another noun


class ClozeCase(unittest.TestCase):
    def test_an_answer_takes_the_sentences_capital(self):
        # the live run lost two cloze cards to "tengo" in "Tengo un coche nuevo."
        self.assertEqual(generate._cloze_case_fix("Tengo un coche nuevo.", "tengo"), ("Tengo un coche nuevo.", "Tengo"))
        self.assertEqual(generate._cloze_case_fix("Contengo la risa.", "tengo"), ("Contengo la risa.", "tengo"))
        self.assertEqual(generate.RULES["es"]["cloze_fix"], generate._cloze_case_fix)

    def test_a_fixed_phrase_is_blanked_whole_not_its_preposition(self):
        # a test run: "Yo echo {{c1::de}} menos" and "Se llevará {{c1::a}} cabo"
        fix = generate.RULES["es"]["cloze_case"]
        self.assertEqual(fix("Yo echo de menos a mis amigos.", "de", "verb_prep", "echar de menos"),
                         ("long_phrase", "echo de menos"))
        self.assertEqual(fix("Se llevará a cabo la inspección mañana.", "a", "verb_prep", "llevar a cabo"),
                         ("long_phrase", "llevará a cabo"))
        self.assertEqual(fix("Echamos De Menos el mar.", "de", "verb_prep", "echar de menos"),
                         ("long_phrase", "Echamos De Menos"))

    def test_a_preposition_at_the_end_stays_a_verb_prep_blank(self):
        fix = generate.RULES["es"]["cloze_case"]
        for sentence, answer, typed in (("¿Os acordáis de la fiesta?", "de", "acordarse de"),
                                        ("Pienso en ti.", "en", "pensar en"),
                                        ("Me di cuenta de todo.", "de", "darse cuenta de")):
            self.assertEqual(fix(sentence, answer, "verb_prep", typed), ("verb_prep", answer), typed)

    def test_anything_unsure_keeps_the_models_blank(self):
        fix = generate.RULES["es"]["cloze_case"]
        self.assertEqual(fix("Tuve en cuenta tu idea.", "en", "verb_prep", "tener en cuenta"),     # irregular form
                         ("verb_prep", "en"))
        self.assertEqual(fix("Echo mucho de menos a mi madre.", "de", "verb_prep", "echar de menos"),  # a word between
                         ("verb_prep", "de"))
        self.assertEqual(fix("Yo echo de menos a mis amigos.", "echo de menos", "long_phrase", "echar de menos"),
                         ("long_phrase", "echo de menos"))
        self.assertEqual(generate.RULES["de"]["cloze_case"]("Ich warte auf dich.", "auf", "verb_prep", "warten auf"),
                         ("verb_prep", "auf"))


class OwnWordFirst(unittest.TestCase):
    """The card's own word in a frame is the pattern most worth learning on its card (the live Native card had
    "no obstante + sustantivo" after "estar + adjetivo")."""

    def extends(self, pattern, word):
        return generate._extends_headword(pattern, word, languages.get("es")["headword_prefixes"],
                                          S.CHECKS["placeholders"])

    def test_the_word_in_a_frame(self):
        self.assertTrue(self.extends("no obstante + sustantivo", "no obstante"))
        self.assertTrue(self.extends("aprovechar la oportunidad de + infinitivo", "aprovechar"))
        self.assertTrue(self.extends("el plazo de algo", "el plazo"))
        self.assertTrue(self.extends("tener que + infinitivo", "tener"))

    def test_other_patterns_and_the_word_alone(self):
        self.assertFalse(self.extends("estar + adjetivo", "no obstante"))
        self.assertFalse(self.extends("dentro del plazo", "el plazo"))          # no frame added
        self.assertFalse(self.extends("mantener algo", "tener"))                # whole words only


class Placeholders(unittest.TestCase):
    """A pattern that only restates the headword is dropped; one that adds a placeholder (algo, alguien) or a
    "+" frame teaches how the phrase is used and stays."""

    def restated(self, pattern, word):
        return generate._self_referential_generic(pattern, word, languages.get("es")["headword_prefixes"],
                                                  placeholders=S.CHECKS["placeholders"])

    def test_restated_and_extended(self):
        self.assertTrue(self.restated("tomar una decisión", "tomar una decisión"))
        self.assertTrue(self.restated("tomar el pelo (modismo)", "tomar el pelo"))
        self.assertFalse(self.restated("tomar una decisión sobre algo", "tomar una decisión"))
        self.assertFalse(self.restated("tomar el pelo a alguien", "tomar el pelo"))
        self.assertFalse(self.restated("darse cuenta de que + indicativo", "darse cuenta"))


class TranslationLanguages(unittest.TestCase):
    def test_a_spanish_learner_picks_from_the_others_and_has_english_by_default(self):
        langs = prompts.translation_languages("es")
        self.assertEqual(len(langs), len(prompts.COMMON_TRANSLATION_LANGS))   # Spanish out, German in
        self.assertNotIn("Spanish", langs)
        self.assertIn("German", langs)
        self.assertEqual(langs[0], "English")
        self.assertEqual(prompts.default_translation_language("es"), "English")

    def test_known_language_for_a_spanish_learner(self):
        allowed = prompts.translation_languages("es")
        for name in ("Spanish", "español", "es"):
            got, warning = generate._known_language(name, None, allowed=allowed)
            self.assertIsNone(got, name)
            self.assertIn("the language the cards teach", warning)
        self.assertEqual(generate._known_language("deutsch", None, allowed=allowed), ("German", None))
        self.assertEqual(generate._known_language("English", None, allowed=allowed), ("English", None))


class LanguageSettings(unittest.TestCase):
    def s(self, cfg):
        return generate.language_settings(cfg, "es")

    def test_spanish_borrows_the_german_cards_translation_language(self):
        self.assertEqual(self.s({}), {"voice": "es-ES-ElviraNeural", "translation": "English",
                                      "translation_voice": "", "secondary": "", "secondary_voice": ""})
        arabic = self.s({"defaults": {"translation_language": "Arabic"}, "voices": {"translation": "ar-SA-ZariyahNeural"}})
        self.assertEqual((arabic["translation"], arabic["translation_voice"]), ("Arabic", "ar-SA-ZariyahNeural"))
        english = self.s({"defaults": {"translation_language": "English"},
                          "voices": {"translation": "en-US-AvaMultilingualNeural"}})
        self.assertEqual((english["translation"], english["translation_voice"]),
                         ("English", "en-US-AvaMultilingualNeural"))

    def test_its_own_block_wins(self):
        cfg = {"defaults": {"translation_language": "Arabic"},
               "languages": {"es": {"voice": "es-MX-DaliaNeural", "translation": "French", "secondary": "English",
                                    "secondary_voice": "en-US-JennyNeural"}}}
        self.assertEqual(self.s(cfg), {"voice": "es-MX-DaliaNeural", "translation": "French", "translation_voice": "",
                                       "secondary": "English", "secondary_voice": "en-US-JennyNeural"})

    def test_names_and_labels(self):
        self.assertEqual(prompts.level_label("Native", "es"), "Native: real spoken Spanish")
        self.assertEqual(languages.resolve("Español"), ("es", None))
        self.assertEqual(languages.get("es")["default_deck"], "Tarkib Spanish")
        self.assertEqual(generate.RULES["es"]["audio_names"], {"target": "tts_es", "translation": "tts_tr"})


class Messages(unittest.TestCase):
    def test_not_spanish(self):
        title, body, kind = providers.friendly_error(RuntimeError('not spanish: "thanks"; suggestion "gracias"'))
        self.assertEqual((title, kind), ("That does not look like Spanish", "retry"))
        self.assertIn('"thanks" as a Spanish word or phrase', body)
        self.assertIn('Did you mean "gracias"?', body)

    def test_register_hint(self):
        hint = S.register_hint("no obstante", ["pero", "aun así"])
        self.assertIn("«no obstante» (Formal)", hint)
        self.assertIn("En el día a día:", hint)
        self.assertEqual(S.register_hint("x", []), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
