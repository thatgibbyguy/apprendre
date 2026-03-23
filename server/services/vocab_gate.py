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


def check_a1_vocab(text: str) -> tuple[bool, float, list[str]]:
    """Check if text uses mostly A1 vocabulary.

    Returns:
        (passes, ratio_known, unknown_words)
        passes is True if ≥70% of content words are A1-level.
    """
    if _nlp is None:
        return True, 1.0, []

    doc = _nlp(text)
    content_lemmas: list[str] = []
    unknown: list[str] = []

    for token in doc:
        if token.pos_ not in _CONTENT_POS:
            continue
        if token.is_punct or token.is_space:
            continue

        lemma = token.lemma_.lower()
        content_lemmas.append(lemma)
        if lemma not in A1_WORDS:
            unknown.append(f"{token.text} ({lemma})")

    if not content_lemmas:
        return True, 1.0, []

    ratio = (len(content_lemmas) - len(unknown)) / len(content_lemmas)
    return ratio >= 0.90, ratio, unknown
