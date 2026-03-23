"""A1 vocabulary gate.

Checks AI responses against a word-frequency list and retries if the
response contains too many words outside A1 vocabulary. Uses spaCy
lemmatization so conjugated forms map back to their infinitive/lemma.
"""

from __future__ import annotations

import spacy
from spacy.tokens import Doc

# Reuse the spaCy model loaded by error_detection (same process).
try:
    _nlp = spacy.load("fr_core_news_md")
except OSError:
    _nlp = None

# POS tags that carry vocabulary meaning (skip function words/punct).
_CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "AUX"}

# English translations for above-A1 lemmas that a constrained LLM may still
# produce.  Keyed by French lemma (lowercase infinitive/singular).  This list
# is intentionally modest — it covers the most common leakage words so the
# learner gets useful tooltip text.  Unknown lemmas fall back to None and the
# frontend shows a generic "new word" label.
TRANSLATIONS: dict[str, str] = {
    # Common verbs above A1
    "dérouler": "to unfold / to go (as in how things go)",
    "se dérouler": "to take place / to unfold",
    "expliquer": "to explain",
    "utiliser": "to use",
    "décider": "to decide",
    "proposer": "to propose / to suggest",
    "sembler": "to seem",
    "devenir": "to become",
    "créer": "to create",
    "produire": "to produce",
    "réaliser": "to realise / to achieve",
    "obtenir": "to obtain / to get",
    "représenter": "to represent",
    "présenter": "to present / to introduce",
    "participer": "to participate",
    "rejoindre": "to join / to meet up with",
    "améliorer": "to improve",
    "organiser": "to organise",
    "gérer": "to manage",
    "profiter": "to take advantage of / to enjoy",
    "dépenser": "to spend (money)",
    "économiser": "to save (money)",
    "réserver": "to reserve / to book",
    "commander": "to order (food/drink)",
    "calculer": "to calculate",
    "expédier": "to send / to dispatch",
    "confirmer": "to confirm",
    "annuler": "to cancel",
    "vérifier": "to check / to verify",
    "installer": "to install / to set up",
    "télécharger": "to download",
    "enregistrer": "to record / to save",
    "imprimer": "to print",
    "brancher": "to plug in",
    "allumer": "to turn on / to light",
    "éteindre": "to turn off / to extinguish",
    "remplacer": "to replace",
    "réparer": "to repair / to fix",
    "nettoyer": "to clean",
    "ranger": "to tidy up / to put away",
    "jeter": "to throw / to throw away",
    "ramasser": "to pick up / to collect",
    "conduire": "to drive",
    "suivre": "to follow",
    "remplir": "to fill",
    "quitter": "to leave (a place)",
    "rejoindre": "to join / to meet",
    "s'asseoir": "to sit down",
    "s'endormir": "to fall asleep",
    "se lever": "to get up",
    "se souvenir": "to remember",
    # Common nouns above A1
    "quartier": "neighbourhood",
    "chemin": "path / way",
    "carrefour": "crossroads / intersection",
    "trottoir": "pavement / sidewalk",
    "feu": "traffic light / fire",
    "panneau": "sign / panel",
    "couloir": "corridor / hallway",
    "ascenseur": "lift / elevator",
    "parking": "car park / parking lot",
    "station": "station",
    "arrêt": "stop (bus/tram)",
    "marché": "market",
    "pharmacie": "pharmacy",
    "boulangerie": "bakery",
    "épicerie": "grocer's shop",
    "librairie": "bookshop",
    "coiffeur": "hairdresser",
    "médecin": "doctor",
    "hôpital": "hospital",
    "urgence": "emergency",
    "rendez-vous": "appointment / meeting",
    "formulaire": "form (document)",
    "carte": "card / map",
    "facture": "bill / invoice",
    "reçu": "receipt",
    "caisse": "checkout / till",
    "rayon": "aisle / shelf (in a shop)",
    "étiquette": "label / tag",
    "taille": "size / waist",
    "pointure": "shoe size",
    "remise": "discount",
    "promotion": "special offer",
    "recette": "recipe",
    "ingrédient": "ingredient",
    "quantité": "quantity",
    "portion": "portion",
    "plat": "dish / flat",
    "entrée": "starter / entrance",
    "dessert": "dessert",
    "boisson": "drink / beverage",
    "addition": "bill (restaurant)",
    "pourboire": "tip (gratuity)",
    "réservation": "reservation / booking",
    "logement": "accommodation / housing",
    "loyer": "rent",
    "charges": "bills / utility charges",
    "propriétaire": "owner / landlord",
    "locataire": "tenant",
    "canapé": "sofa / couch",
    "fauteuil": "armchair",
    "étagère": "shelf",
    "placard": "cupboard / closet",
    "tiroir": "drawer",
    "robinet": "tap / faucet",
    "douche": "shower",
    "baignoire": "bathtub",
    "serviette": "towel / napkin",
    "couverture": "blanket / cover",
    "oreiller": "pillow",
    "matelas": "mattress",
    "rideau": "curtain",
    "tapis": "rug / carpet",
    "vêtement": "clothing / garment",
    "manteau": "coat",
    "veste": "jacket",
    "pantalon": "trousers / pants",
    "chemise": "shirt",
    "robe": "dress",
    "jupe": "skirt",
    "chaussure": "shoe",
    "chaussette": "sock",
    "chapeau": "hat",
    "écharpe": "scarf",
    "gant": "glove",
    "ceinture": "belt",
    "lunette": "glasses (spectacles)",
    # Common adjectives above A1
    "magnifique": "magnificent / wonderful",
    "formidable": "great / tremendous",
    "merveilleux": "marvellous / wonderful",
    "délicieux": "delicious",
    "savoureux": "tasty / flavourful",
    "frais": "fresh / cool",
    "tiède": "lukewarm / mild",
    "épicé": "spicy",
    "sucré": "sweet",
    "salé": "salty / savoury",
    "amer": "bitter",
    "léger": "light / lightweight",
    "lourd": "heavy",
    "solide": "solid / sturdy",
    "fragile": "fragile / delicate",
    "pratique": "practical / handy",
    "confortable": "comfortable",
    "calme": "calm / quiet",
    "bruyant": "noisy / loud",
    "lumineux": "bright / luminous",
    "sombre": "dark / gloomy",
    "spacieux": "spacious",
    "étroit": "narrow / tight",
    "moderne": "modern",
    "ancien": "old / former / ancient",
    "usé": "worn out / used",
    "sale": "dirty",
    "rapide": "fast / quick",
    "lent": "slow",
    "fort": "strong / loud",
    "doux": "soft / gentle / sweet",
    "dur": "hard / tough",
    "souple": "flexible / supple",
    "rigide": "rigid / stiff",
    "désagréable": "unpleasant",
    "utile": "useful",
    "inutile": "useless",
    "disponible": "available",
    "occupé": "busy / occupied",
    "pressé": "in a hurry",
    "désolé": "sorry",
    "ravi": "delighted",
    "satisfait": "satisfied",
    "déçu": "disappointed",
    "surpris": "surprised",
    "inquiet": "worried / anxious",
    "soulagé": "relieved",
    "fier": "proud",
    "jaloux": "jealous",
    "curieux": "curious",
    # Common adverbs above A1
    "notamment": "notably / in particular",
    "cependant": "however",
    "pourtant": "yet / however / still",
    "néanmoins": "nevertheless",
    "ainsi": "thus / in this way",
    "finalement": "finally / eventually",
    "récemment": "recently",
    "actuellement": "currently / at present",
    "généralement": "generally",
    "particulièrement": "particularly",
    "exactement": "exactly",
    "absolument": "absolutely",
    "certainement": "certainly",
    "probablement": "probably",
    "rapidement": "quickly / rapidly",
    "lentement": "slowly",
    "doucement": "gently / softly / slowly",
    "fortement": "strongly / greatly",
    "simplement": "simply",
    "clairement": "clearly",
    "directement": "directly",
    "ensemble": "together",
    "séparément": "separately",
    "partout": "everywhere",
    "nulle part": "nowhere",
    "quelque part": "somewhere",
    "n'importe où": "anywhere",
    "autrefois": "formerly / in the past",
    "désormais": "from now on / henceforth",
    "longtemps": "for a long time",
    "parfaitement": "perfectly",
}

# A1 vocabulary — ~500 most common French lemmas a beginner would know.
# Verbs as infinitives, nouns as singular, all lowercase.
A1_WORDS: set[str] = {
    # Greetings & expressions
    "bonjour", "bonsoir", "salut", "merci", "pardon", "oui", "non",
    "bien", "mal", "super", "cool", "bah", "bof", "ouais", "allez",
    "enchanté", "bravo", "attention", "courage", "voilà",
    "d'accord", "ok", "hein", "quoi", "tiens", "bon",

    # Pronouns (lemmatized)
    "je", "tu", "il", "elle", "on", "nous", "vous", "ce", "ça",
    "moi", "toi", "lui", "y", "en", "se", "qui", "que",

    # Verbs (infinitives)
    "être", "avoir", "aller", "faire", "pouvoir", "vouloir", "devoir",
    "savoir", "dire", "venir", "voir", "prendre", "mettre", "donner",
    "parler", "manger", "boire", "dormir", "jouer", "regarder",
    "écouter", "travailler", "habiter", "aimer", "adorer", "détester",
    "préférer", "acheter", "payer", "chercher", "trouver", "demander",
    "répondre", "comprendre", "apprendre", "lire", "écrire",
    "commencer", "finir", "ouvrir", "fermer", "partir", "arriver",
    "entrer", "sortir", "monter", "descendre", "rester", "tomber",
    "marcher", "courir", "attendre", "croire", "connaître", "penser",
    "espérer", "essayer", "porter", "changer", "appeler", "cuisiner",
    "préparer", "chanter", "danser", "nager", "voyager", "visiter",
    "rencontrer", "inviter", "aider", "montrer", "raconter", "oublier",
    "choisir", "accepter", "permettre", "falloir", "pleuvoir",
    "passer", "tourner", "traverser", "continuer", "arrêter",
    "répéter", "rentrer", "rappeler", "plaire", "servir", "tenir",
    "perdre", "gagner", "envoyer", "recevoir", "offrir", "lever",
    "coucher", "laver", "habiller", "promener", "réveiller",
    "asseoir", "occuper", "intéresser", "excuser", "sentir",

    # Nouns — family
    "famille", "père", "mère", "parent", "enfant", "fils", "fille",
    "frère", "sœur", "mari", "femme", "bébé", "ami", "copain",
    "voisin", "personne", "homme", "garçon", "gens", "monde",

    # Nouns — home
    "maison", "appartement", "chambre", "cuisine", "salon", "jardin",
    "porte", "fenêtre", "escalier", "étage", "clé", "immeuble",

    # Nouns — objects
    "table", "chaise", "lit", "bureau", "lampe", "télé",
    "ordinateur", "téléphone", "livre", "sac", "photo", "cadeau",
    "parapluie", "montre", "truc", "chose",

    # Nouns — food
    "pain", "beurre", "fromage", "lait", "œuf", "viande", "poulet",
    "poisson", "riz", "pâtes", "soupe", "salade", "légume", "fruit",
    "pomme", "orange", "banane", "tomate", "gâteau", "chocolat",
    "glace", "eau", "café", "thé", "jus", "vin", "bière",
    "repas", "restaurant", "menu",

    # Nouns — city & transport
    "ville", "rue", "parc", "magasin", "école", "gare", "cinéma", "musée",
    "voiture", "bus", "train", "vélo", "billet",

    # Nouns — work
    "travail", "bureau", "métier", "patron", "projet",

    # Nouns — body
    "tête", "main", "pied", "dos", "dent", "cœur",

    # Nouns — time
    "temps", "heure", "minute", "moment", "fois",
    "jour", "journée", "matin", "soir", "nuit",
    "semaine", "week-end", "mois", "an", "année",
    "vacances", "fête", "anniversaire",

    # Nouns — weather & nature
    "soleil", "pluie", "neige", "vent", "ciel",
    "mer", "montagne", "animal", "chien", "chat",

    # Nouns — abstract
    "vie", "amour", "argent", "prix", "couleur",
    "nom", "âge", "musique", "film", "sport", "jeu",
    "histoire", "nouvelle", "idée", "problème",
    "question", "réponse", "erreur", "aide", "envie",
    "début", "fin", "côté", "place", "cours", "langue", "mot",

    # Adjectives
    "bon", "mauvais", "grand", "petit", "gros",
    "beau", "bel", "belle", "joli", "nouveau", "nouvel", "vieux", "vieil", "jeune",
    "long", "court", "haut", "chaud", "froid",
    "premier", "dernier", "prochain", "content", "heureux",
    "triste", "fatigué", "malade", "gentil", "drôle",
    "facile", "difficile", "important", "intéressant",
    "gratuit", "cher", "ouvert", "fermé", "plein", "vide",
    "propre", "prêt", "libre", "seul", "même", "autre",
    "tout", "blanc", "noir", "rouge", "bleu", "vert", "jaune",
    "vrai", "faux", "sûr", "normal", "simple",
    "français", "anglais", "agréable", "parfait",
    "super", "grave", "droit", "gauche", "crevé",
    "tranquille", "sympa", "bizarre", "énorme",

    # Adverbs
    "très", "trop", "assez", "peu", "beaucoup", "plus", "moins",
    "aussi", "encore", "déjà", "toujours", "souvent", "parfois",
    "jamais", "vite", "ici", "là", "maintenant", "bientôt",
    "tôt", "tard", "enfin", "ensuite", "après", "avant",
    "pendant", "seulement", "vraiment", "environ", "presque",
    "plutôt", "surtout", "pas", "ne", "aujourd'hui", "hier",
    "demain",

    # Prepositions
    "à", "de", "en", "dans", "avec", "sans", "pour", "par",
    "sur", "sous", "entre", "devant", "derrière", "vers", "chez",

    # Conjunctions
    "et", "ou", "mais", "donc", "alors", "parce", "si",
    "quand", "comme",

    # Question words
    "où", "comment", "pourquoi", "combien", "quel",

    # Numbers
    "un", "deux", "trois", "quatre", "cinq", "six", "sept",
    "huit", "neuf", "dix", "vingt", "trente", "cent", "mille",

    # Days
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
    "dimanche",

    # Months / seasons
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    "printemps", "été", "automne", "hiver",
}


def check_a1_vocab(
    text: str,
) -> tuple[bool, float, list[dict[str, str | None]]]:
    """Check if text uses mostly A1 vocabulary.

    Returns:
        (passes, ratio_known, unknown_words)

        passes is True if ≥90% of content words are A1-level.

        unknown_words is a list of dicts, one per above-level token::

            {
                "word":        str,        # surface form as it appears in the text
                "lemma":       str,        # French base form / infinitive
                "translation": str | None, # English translation if known, else None
            }
    """
    if _nlp is None:
        return True, 1.0, []

    doc = _nlp(text)
    content_lemmas: list[str] = []
    unknown: list[dict[str, str | None]] = []

    for token in doc:
        if token.pos_ not in _CONTENT_POS:
            continue
        if token.is_punct or token.is_space:
            continue

        lemma = token.lemma_.lower()
        content_lemmas.append(lemma)
        if lemma not in A1_WORDS:
            unknown.append(
                {
                    "word": token.text,
                    "lemma": lemma,
                    "translation": TRANSLATIONS.get(lemma),
                }
            )

    if not content_lemmas:
        return True, 1.0, []

    ratio = (len(content_lemmas) - len(unknown)) / len(content_lemmas)
    return ratio >= 0.90, ratio, unknown
