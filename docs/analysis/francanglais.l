%{
/* ------------------------------------------------------------------
 * francanglais.l - lexical specification for Yaoundé street speech.
 * Generated from dictionary/*.md by fca/regexspec.py. Do not edit by
 * hand: regenerate with  python main.py regex --flex
 *
 * Build:  flex francanglais.l && cc lex.yy.c -o francanglais
 * Run:    ./francanglais < corpus.txt
 * ------------------------------------------------------------------ */
#include <stdio.h>
static void emit(const char *cat, const char *lexeme) {
    printf("%-8s %s\n", cat, lexeme);
}
%}

%option noyywrap
%option caseless

DIGIT   [0-9]
LETTER  [A-Za-z]
WORD    {LETTER}+('{LETTER}+)?

%%

"tu vas faire comment"       { emit("INTERJ", yytext); }
"on va faire comment"        { emit("INTERJ", yytext); }
"debrouillardise"            { emit("NOUN", yytext); }
"le pays est dur"            { emit("INTERJ", yytext); }
"on est ensemble"            { emit("INTERJ", yytext); }
"s'il vous plait"            { emit("INTERJ", yytext); }
"se debrouiller"             { emit("VERB", yytext); }
"c'est comment"              { emit("QWORD", yytext); }
"embouteillage"              { emit("NOUN", yytext); }
"bayam-sellam"               { emit("NOUN", yytext); }
"bendskin man"               { emit("NOUN", yytext); }
"bushfaia man"               { emit("NOUN", yytext); }
"dernier prix"               { emit("NOUN", yytext); }
"aujourd'hui"                { emit("ADV", yytext); }
"ca va aller"                { emit("INTERJ", yytext); }
"call-boxeur"                { emit("NOUN", yytext); }
"kwata pipul"                { emit("NOUN", yytext); }
"mange-mille"                { emit("NOUN", yytext); }
"mbeng fever"                { emit("NOUN", yytext); }
"njama njama"                { emit("NOUN", yytext); }
"ambianceur"                 { emit("NOUN", yytext); }
"bushfaller"                 { emit("NOUN", yytext); }
"chek point"                 { emit("NOUN", yytext); }
"drai sisin"                 { emit("NOUN", yytext); }
"longcrayon"                 { emit("NOUN", yytext); }
"maintenant"                 { emit("ADV", yytext); }
"mbenguiste"                 { emit("NOUN", yytext); }
"nourriture"                 { emit("NOUN", yytext); }
"professeur"                 { emit("NOUN", yytext); }
"travailler"                 { emit("VERB", yytext); }
"universite"                 { emit("NOUN", yytext); }
"carrefour"                  { emit("NOUN", yytext); }
"chauffeur"                  { emit("NOUN", yytext); }
"chuk hand"                  { emit("VERB", yytext); }
"cinquante"                  { emit("NUM", yytext); }
"delestage"                  { emit("NOUN", yytext); }
"descendre"                  { emit("VERB", yytext); }
"difficile"                  { emit("ADJ", yytext); }
"garri boy"                  { emit("NOUN", yytext); }
"gudivning"                  { emit("INTERJ", yytext); }
"gudmoning"                  { emit("INTERJ", yytext); }
"konekshon"                  { emit("NOUN", yytext); }
"kwatt boy"                  { emit("NOUN", yytext); }
"no wahala"                  { emit("INTERJ", yytext); }
"pala pala"                  { emit("NOUN", yytext); }
"parce que"                  { emit("CONJ", yytext); }
"poulet dg"                  { emit("NOUN", yytext); }
"prix fixe"                  { emit("NOUN", yytext); }
"puff-puff"                  { emit("NOUN", yytext); }
"ren sisin"                  { emit("NOUN", yytext); }
"ren sison"                  { emit("NOUN", yytext); }
"sauveteur"                  { emit("NOUN", yytext); }
"se lancer"                  { emit("VERB", yytext); }
"seulement"                  { emit("PART", yytext); }
"smol smol"                  { emit("ADV", yytext); }
"smol taim"                  { emit("ADV", yytext); }
"tchatcher"                  { emit("VERB", yytext); }
"telephone"                  { emit("NOUN", yytext); }
"tournedos"                  { emit("NOUN", yytext); }
"travaille"                  { emit("VERB", yytext); }
"tu es how"                  { emit("QWORD", yytext); }
"wata wata"                  { emit("NOUN", yytext); }
"wetin dei"                  { emit("INTERJ", yytext); }
"zero-zero"                  { emit("NOUN", yytext); }
"ambiance"                   { emit("NOUN", yytext); }
"attendre"                   { emit("VERB", yytext); }
"beaucoup"                   { emit("ADV", yytext); }
"beignets"                   { emit("NOUN", yytext); }
"bendskin"                   { emit("NOUN", yytext); }
"boutique"                   { emit("NOUN", yytext); }
"bring am"                   { emit("VERB", yytext); }
"call box"                   { emit("NOUN", yytext); }
"chercher"                   { emit("VERB", yytext); }
"comme ca"                   { emit("ADV", yytext); }
"couscous"                   { emit("NOUN", yytext); }
"demander"                   { emit("VERB", yytext); }
"djoumbai"                   { emit("NOUN", yytext); }
"ensemble"                   { emit("ADV", yytext); }
"etudiant"                   { emit("NOUN", yytext); }
"faya wud"                   { emit("NOUN", yytext); }
"feymania"                   { emit("NOUN", yytext); }
"granmami"                   { emit("NOUN", yytext); }
"granpapa"                   { emit("NOUN", yytext); }
"je wanda"                   { emit("NOUN", yytext); }
"jenerato"                   { emit("NOUN", yytext); }
"junction"                   { emit("NOUN", yytext); }
"kam chop"                   { emit("INTERJ", yytext); }
"kongossa"                   { emit("VERB", yytext); }
"na wa oh"                   { emit("INTERJ", yytext); }
"ngataman"                   { emit("NOUN", yytext); }
"ngrimbah"                   { emit("NOUN", yytext); }
"no bi so"                   { emit("INTERJ", yytext); }
"personne"                   { emit("NEG", yytext); }
"polisman"                   { emit("NOUN", yytext); }
"pourquoi"                   { emit("QWORD", yytext); }
"probleme"                   { emit("NOUN", yytext); }
"quartier"                   { emit("NOUN", yytext); }
"regarder"                   { emit("VERB", yytext); }
"se saper"                   { emit("VERB", yytext); }
"toujours"                   { emit("ADV", yytext); }
"y a quoi"                   { emit("QWORD", yytext); }
"acheter"                    { emit("VERB", yytext); }
"affaire"                    { emit("NOUN", yytext); }
"aftanun"                    { emit("NOUN", yytext); }
"appeler"                    { emit("VERB", yytext); }
"appelle"                    { emit("VERB", yytext); }
"arriver"                    { emit("VERB", yytext); }
"ashouka"                    { emit("INTERJ", yytext); }
"attends"                    { emit("VERB", yytext); }
"bargain"                    { emit("VERB", yytext); }
"benskin"                    { emit("NOUN", yytext); }
"bizness"                    { emit("NOUN", yytext); }
"bonjour"                    { emit("INTERJ", yytext); }
"bonsoir"                    { emit("INTERJ", yytext); }
"chakara"                    { emit("VERB", yytext); }
"cherche"                    { emit("VERB", yytext); }
"circuit"                    { emit("NOUN", yytext); }
"combien"                    { emit("QWORD", yytext); }
"comment"                    { emit("QWORD", yytext); }
"content"                    { emit("ADJ", yytext); }
"coupure"                    { emit("NOUN", yytext); }
"courant"                    { emit("NOUN", yytext); }
"dem tin"                    { emit("DET", yytext); }
"demande"                    { emit("VERB", yytext); }
"dernier"                    { emit("NUM", yytext); }
"descend"                    { emit("VERB", yytext); }
"eni man"                    { emit("PRON", yytext); }
"essence"                    { emit("NOUN", yytext); }
"fatigue"                    { emit("ADJ", yytext); }
"gratuit"                    { emit("ADJ", yytext); }
"gudnait"                    { emit("INTERJ", yytext); }
"hala me"                    { emit("VERB", yytext); }
"handred"                    { emit("NUM", yytext); }
"hopital"                    { emit("NOUN", yytext); }
"hospita"                    { emit("NOUN", yytext); }
"jusqu'a"                    { emit("PREP", yytext); }
"kam bak"                    { emit("VERB", yytext); }
"kari go"                    { emit("VERB", yytext); }
"kongosa"                    { emit("NOUN", yytext); }
"kongosa"                    { emit("VERB", yytext); }
"kontrol"                    { emit("NOUN", yytext); }
"kwakoko"                    { emit("NOUN", yytext); }
"kwenchi"                    { emit("VERB", yytext); }
"lumiere"                    { emit("NOUN", yytext); }
"marcher"                    { emit("VERB", yytext); }
"matango"                    { emit("NOUN", yytext); }
"mauvais"                    { emit("ADJ", yytext); }
"mbourou"                    { emit("NOUN", yytext); }
"naw naw"                    { emit("ADV", yytext); }
"ndoutou"                    { emit("NOUN", yytext); }
"nouveau"                    { emit("ADJ", yytext); }
"odontol"                    { emit("NOUN", yytext); }
"ol ting"                    { emit("PRON", yytext); }
"palabre"                    { emit("NOUN", yytext); }
"partout"                    { emit("ADV", yytext); }
"pendant"                    { emit("PREP", yytext); }
"peuvent"                    { emit("TMA", yytext); }
"plantin"                    { emit("NOUN", yytext); }
"pof-pof"                    { emit("NOUN", yytext); }
"pouvons"                    { emit("TMA", yytext); }
"premier"                    { emit("NUM", yytext); }
"prendre"                    { emit("VERB", yytext); }
"put han"                    { emit("VERB", yytext); }
"regarde"                    { emit("VERB", yytext); }
"rentrer"                    { emit("VERB", yytext); }
"rispekt"                    { emit("NOUN", yytext); }
"semaine"                    { emit("NOUN", yytext); }
"shoulda"                    { emit("NOUN", yytext); }
"sojaman"                    { emit("NOUN", yytext); }
"souvent"                    { emit("ADV", yytext); }
"station"                    { emit("NOUN", yytext); }
"stranga"                    { emit("NOUN", yytext); }
"tank yu"                    { emit("INTERJ", yytext); }
"tif man"                    { emit("NOUN", yytext); }
"travail"                    { emit("NOUN", yytext); }
"trouver"                    { emit("VERB", yytext); }
"tu moch"                    { emit("ADV", yytext); }
"village"                    { emit("NOUN", yytext); }
"voiture"                    { emit("NOUN", yytext); }
"yestade"                    { emit("ADV", yytext); }
"achete"                     { emit("VERB", yytext); }
"allons"                     { emit("TMA", yytext); }
"argent"                     { emit("NOUN", yytext); }
"arrive"                     { emit("VERB", yytext); }
"attend"                     { emit("VERB", yytext); }
"autsai"                     { emit("PREP", yytext); }
"avance"                     { emit("NOUN", yytext); }
"bihain"                     { emit("PREP", yytext); }
"bloque"                     { emit("NOUN", yytext); }
"boulot"                     { emit("NOUN", yytext); }
"bureau"                     { emit("NOUN", yytext); }
"cadeau"                     { emit("NOUN", yytext); }
"chaque"                     { emit("DET", yytext); }
"charge"                     { emit("VERB", yytext); }
"clando"                     { emit("NOUN", yytext); }
"client"                     { emit("NOUN", yytext); }
"de kam"                     { emit("VERB", yytext); }
"demain"                     { emit("ADV", yytext); }
"depuis"                     { emit("PREP", yytext); }
"donner"                     { emit("VERB", yytext); }
"ekwang"                     { emit("NOUN", yytext); }
"encore"                     { emit("ADV", yytext); }
"enfant"                     { emit("NOUN", yytext); }
"entrer"                     { emit("VERB", yytext); }
"examen"                     { emit("NOUN", yytext); }
"facile"                     { emit("ADJ", yytext); }
"feyman"                     { emit("NOUN", yytext); }
"fulish"                     { emit("ADJ", yytext); }
"gauler"                     { emit("VERB", yytext); }
"hambok"                     { emit("VERB", yytext); }
"hia me"                     { emit("VERB", yytext); }
"hongri"                     { emit("ADJ", yytext); }
"hostel"                     { emit("NOUN", yytext); }
"how fa"                     { emit("INTERJ", yytext); }
"ivning"                     { emit("NOUN", yytext); }
"jamais"                     { emit("ADV", yytext); }
"kalaba"                     { emit("NOUN", yytext); }
"kampus"                     { emit("NOUN", yytext); }
"kasada"                     { emit("NOUN", yytext); }
"kichin"                     { emit("NOUN", yytext); }
"kondre"                     { emit("NOUN", yytext); }
"kurent"                     { emit("NOUN", yytext); }
"la-bas"                     { emit("ADV", yytext); }
"laisse"                     { emit("VERB", yytext); }
"lancer"                     { emit("VERB", yytext); }
"lekcha"                     { emit("NOUN", yytext); }
"maison"                     { emit("NOUN", yytext); }
"malade"                     { emit("ADJ", yytext); }
"manger"                     { emit("VERB", yytext); }
"marche"                     { emit("NOUN", yytext); }
"marche"                     { emit("VERB", yytext); }
"mbindi"                     { emit("ADJ", yytext); }
"moning"                     { emit("NOUN", yytext); }
"motard"                     { emit("NOUN", yytext); }
"na lai"                     { emit("INTERJ", yytext); }
"na tru"                     { emit("INTERJ", yytext); }
"netwok"                     { emit("NOUN", yytext); }
"nobodi"                     { emit("PRON", yytext); }
"nyanga"                     { emit("NOUN", yytext); }
"nyanga"                     { emit("ADJ", yytext); }
"nyango"                     { emit("NOUN", yytext); }
"nyoxer"                     { emit("VERB", yytext); }
"ol man"                     { emit("PRON", yytext); }
"palava"                     { emit("NOUN", yytext); }
"pardon"                     { emit("INTERJ", yytext); }
"parler"                     { emit("VERB", yytext); }
"partir"                     { emit("VERB", yytext); }
"passer"                     { emit("VERB", yytext); }
"pastor"                     { emit("NOUN", yytext); }
"patron"                     { emit("NOUN", yytext); }
"plenti"                     { emit("ADJ", yytext); }
"police"                     { emit("NOUN", yytext); }
"propre"                     { emit("ADJ", yytext); }
"quatre"                     { emit("NUM", yytext); }
"quelle"                     { emit("QWORD", yytext); }
"rapide"                     { emit("ADJ", yytext); }
"rentre"                     { emit("VERB", yytext); }
"reseau"                     { emit("NOUN", yytext); }
"rester"                     { emit("VERB", yytext); }
"sapeur"                     { emit("NOUN", yytext); }
"savoir"                     { emit("VERB", yytext); }
"shidon"                     { emit("VERB", yytext); }
"sissia"                     { emit("VERB", yytext); }
"soleil"                     { emit("NOUN", yytext); }
"sommes"                     { emit("COP", yytext); }
"sortir"                     { emit("VERB", yytext); }
"stanap"                     { emit("VERB", yytext); }
"taisti"                     { emit("ADJ", yytext); }
"tausin"                     { emit("NUM", yytext); }
"tchoko"                     { emit("NOUN", yytext); }
"titcha"                     { emit("NOUN", yytext); }
"tranga"                     { emit("ADJ", yytext); }
"triste"                     { emit("ADJ", yytext); }
"trobul"                     { emit("NOUN", yytext); }
"trouve"                     { emit("VERB", yytext); }
"tumoro"                     { emit("ADV", yytext); }
"twenti"                     { emit("NUM", yytext); }
"vendre"                     { emit("VERB", yytext); }
"viande"                     { emit("NOUN", yytext); }
"wahala"                     { emit("NOUN", yytext); }
"wan go"                     { emit("VERB", yytext); }
"wi own"                     { emit("POSS", yytext); }
"witaut"                     { emit("PREP", yytext); }
"afofo"                      { emit("NOUN", yytext); }
"akara"                      { emit("NOUN", yytext); }
"aller"                      { emit("VERB", yytext); }
"allez"                      { emit("TMA", yytext); }
"alors"                      { emit("PART", yytext); }
"annee"                      { emit("NOUN", yytext); }
"apres"                      { emit("PREP", yytext); }
"ashia"                      { emit("INTERJ", yytext); }
"autre"                      { emit("ADJ", yytext); }
"avant"                      { emit("PREP", yytext); }
"avoir"                      { emit("VERB", yytext); }
"avons"                      { emit("TMA", yytext); }
"belle"                      { emit("ADJ", yytext); }
"bikos"                      { emit("CONJ", yytext); }
"bizgo"                      { emit("NOUN", yytext); }
"boire"                      { emit("VERB", yytext); }
"bonne"                      { emit("ADJ", yytext); }
"broda"                      { emit("NOUN", yytext); }
"c'est"                      { emit("COP", yytext); }
"cette"                      { emit("DET", yytext); }
"chaud"                      { emit("ADJ", yytext); }
"chenj"                      { emit("NOUN", yytext); }
"chose"                      { emit("NOUN", yytext); }
"chuch"                      { emit("NOUN", yytext); }
"comme"                      { emit("CONJ", yytext); }
"cours"                      { emit("NOUN", yytext); }
"damer"                      { emit("VERB", yytext); }
"djibs"                      { emit("NOUN", yytext); }
"djoba"                      { emit("NOUN", yytext); }
"dokta"                      { emit("NOUN", yytext); }
"donne"                      { emit("VERB", yytext); }
"drink"                      { emit("VERB", yytext); }
"ecole"                      { emit("NOUN", yytext); }
"egusi"                      { emit("NOUN", yytext); }
"ekiee"                      { emit("NOUN", yytext); }
"eleve"                      { emit("NOUN", yytext); }
"elles"                      { emit("PRON", yytext); }
"empti"                      { emit("ADJ", yytext); }
"entre"                      { emit("VERB", yytext); }
"entre"                      { emit("PREP", yytext); }
"etait"                      { emit("COP", yytext); }
"faire"                      { emit("VERB", yytext); }
"femme"                      { emit("NOUN", yytext); }
"fifti"                      { emit("NUM", yytext); }
"finga"                      { emit("NOUN", yytext); }
"frere"                      { emit("NOUN", yytext); }
"fresh"                      { emit("ADJ", yytext); }
"froid"                      { emit("ADJ", yytext); }
"fulop"                      { emit("ADJ", yytext); }
"garri"                      { emit("NOUN", yytext); }
"gombo"                      { emit("NOUN", yytext); }
"grand"                      { emit("ADJ", yytext); }
"grong"                      { emit("NOUN", yytext); }
"hamas"                      { emit("QWORD", yytext); }
"helep"                      { emit("VERB", yytext); }
"heure"                      { emit("NOUN", yytext); }
"homme"                      { emit("NOUN", yytext); }
"insai"                      { emit("PREP", yytext); }
"jeune"                      { emit("ADJ", yytext); }
"kamer"                      { emit("NOUN", yytext); }
"kanda"                      { emit("NOUN", yytext); }
"karfu"                      { emit("NOUN", yytext); }
"kombi"                      { emit("NOUN", yytext); }
"komot"                      { emit("VERB", yytext); }
"kredi"                      { emit("NOUN", yytext); }
"krezi"                      { emit("ADJ", yytext); }
"kwata"                      { emit("NOUN", yytext); }
"kwatt"                      { emit("NOUN", yytext); }
"maket"                      { emit("NOUN", yytext); }
"mange"                      { emit("VERB", yytext); }
"masho"                      { emit("NOUN", yytext); }
"massa"                      { emit("NOUN", yytext); }
"mater"                      { emit("NOUN", yytext); }
"matin"                      { emit("NOUN", yytext); }
"mbeng"                      { emit("NOUN", yytext); }
"merci"                      { emit("INTERJ", yytext); }
"mille"                      { emit("NUM", yytext); }
"mimba"                      { emit("VERB", yytext); }
"mimbo"                      { emit("NOUN", yytext); }
"monde"                      { emit("NOUN", yytext); }
"monte"                      { emit("VERB", yytext); }
"na so"                      { emit("INTERJ", yytext); }
"na wa"                      { emit("INTERJ", yytext); }
"ndole"                      { emit("NOUN", yytext); }
"ndolo"                      { emit("NOUN", yytext); }
"ndoss"                      { emit("NOUN", yytext); }
"ngata"                      { emit("NOUN", yytext); }
"ngeme"                      { emit("NOUN", yytext); }
"notin"                      { emit("PRON", yytext); }
"notre"                      { emit("POSS", yytext); }
"ontop"                      { emit("PREP", yytext); }
"panne"                      { emit("NOUN", yytext); }
"parle"                      { emit("VERB", yytext); }
"pasho"                      { emit("NOUN", yytext); }
"passe"                      { emit("VERB", yytext); }
"pater"                      { emit("NOUN", yytext); }
"payer"                      { emit("VERB", yytext); }
"petit"                      { emit("NOUN", yytext); }
"petit"                      { emit("ADJ", yytext); }
"pikin"                      { emit("NOUN", yytext); }
"pipul"                      { emit("NOUN", yytext); }
"place"                      { emit("NOUN", yytext); }
"plein"                      { emit("ADJ", yytext); }
"pluie"                      { emit("NOUN", yytext); }
"prais"                      { emit("NOUN", yytext); }
"prend"                      { emit("VERB", yytext); }
"quand"                      { emit("CONJ", yytext); }
"redus"                      { emit("VERB", yytext); }
"reste"                      { emit("VERB", yytext); }
"route"                      { emit("NOUN", yytext); }
"salut"                      { emit("INTERJ", yytext); }
"sango"                      { emit("NOUN", yytext); }
"saper"                      { emit("VERB", yytext); }
"sekon"                      { emit("NUM", yytext); }
"seven"                      { emit("NUM", yytext); }
"sidon"                      { emit("VERB", yytext); }
"sista"                      { emit("NOUN", yytext); }
"soeur"                      { emit("NOUN", yytext); }
"sotai"                      { emit("CONJ", yytext); }
"taxer"                      { emit("VERB", yytext); }
"tchat"                      { emit("VERB", yytext); }
"tchop"                      { emit("VERB", yytext); }
"tebul"                      { emit("NOUN", yytext); }
"temps"                      { emit("NOUN", yytext); }
"toute"                      { emit("DET", yytext); }
"trois"                      { emit("NUM", yytext); }
"tuyau"                      { emit("NOUN", yytext); }
"twelv"                      { emit("NUM", yytext); }
"venir"                      { emit("VERB", yytext); }
"vient"                      { emit("VERB", yytext); }
"vieux"                      { emit("ADJ", yytext); }
"vilej"                      { emit("NOUN", yytext); }
"ville"                      { emit("NOUN", yytext); }
"vingt"                      { emit("NUM", yytext); }
"voila"                      { emit("PART", yytext); }
"votre"                      { emit("POSS", yytext); }
"wanda"                      { emit("VERB", yytext); }
"wekop"                      { emit("VERB", yytext); }
"wetin"                      { emit("QWORD", yytext); }
"windo"                      { emit("NOUN", yytext); }
"woman"                      { emit("NOUN", yytext); }
"wusai"                      { emit("QWORD", yytext); }
"abeg"                       { emit("PART", yytext); }
"afta"                       { emit("PREP", yytext); }
"ansa"                       { emit("VERB", yytext); }
"avec"                       { emit("PREP", yytext); }
"avez"                       { emit("TMA", yytext); }
"beau"                       { emit("ADJ", yytext); }
"bele"                       { emit("NOUN", yytext); }
"bien"                       { emit("ADV", yytext); }
"bifo"                       { emit("PREP", yytext); }
"bins"                       { emit("NOUN", yytext); }
"bita"                       { emit("ADJ", yytext); }
"blad"                       { emit("NOUN", yytext); }
"blok"                       { emit("VERB", yytext); }
"bobi"                       { emit("NOUN", yytext); }
"boit"                       { emit("VERB", yytext); }
"bolo"                       { emit("NOUN", yytext); }
"bosh"                       { emit("VERB", yytext); }
"boss"                       { emit("NOUN", yytext); }
"bred"                       { emit("NOUN", yytext); }
"brok"                       { emit("VERB", yytext); }
"bush"                       { emit("NOUN", yytext); }
"ceci"                       { emit("PRON", yytext); }
"cela"                       { emit("PRON", yytext); }
"cent"                       { emit("NUM", yytext); }
"chai"                       { emit("INTERJ", yytext); }
"cher"                       { emit("ADJ", yytext); }
"ches"                       { emit("NOUN", yytext); }
"chez"                       { emit("PREP", yytext); }
"chia"                       { emit("NOUN", yytext); }
"chif"                       { emit("NOUN", yytext); }
"chip"                       { emit("ADJ", yytext); }
"chop"                       { emit("NOUN", yytext); }
"chop"                       { emit("VERB", yytext); }
"chuk"                       { emit("VERB", yytext); }
"cinq"                       { emit("NUM", yytext); }
"dans"                       { emit("VERB", yytext); }
"dans"                       { emit("PREP", yytext); }
"dash"                       { emit("NOUN", yytext); }
"deja"                       { emit("PART", yytext); }
"deux"                       { emit("NUM", yytext); }
"dire"                       { emit("VERB", yytext); }
"dois"                       { emit("TMA", yytext); }
"doit"                       { emit("TMA", yytext); }
"donc"                       { emit("CONJ", yytext); }
"doti"                       { emit("NOUN", yytext); }
"doti"                       { emit("ADJ", yytext); }
"drop"                       { emit("VERB", yytext); }
"ehen"                       { emit("INTERJ", yytext); }
"ekie"                       { emit("INTERJ", yytext); }
"elle"                       { emit("PRON", yytext); }
"enta"                       { emit("VERB", yytext); }
"etes"                       { emit("COP", yytext); }
"etre"                       { emit("VERB", yytext); }
"fain"                       { emit("VERB", yytext); }
"fain"                       { emit("ADJ", yytext); }
"fais"                       { emit("VERB", yytext); }
"fait"                       { emit("VERB", yytext); }
"faiv"                       { emit("NUM", yytext); }
"faut"                       { emit("TMA", yytext); }
"faux"                       { emit("ADJ", yytext); }
"faya"                       { emit("NOUN", yytext); }
"fill"                       { emit("VERB", yytext); }
"fish"                       { emit("NOUN", yytext); }
"fiul"                       { emit("NOUN", yytext); }
"fort"                       { emit("ADJ", yytext); }
"fren"                       { emit("NOUN", yytext); }
"fufu"                       { emit("NOUN", yytext); }
"garr"                       { emit("NOUN", yytext); }
"gars"                       { emit("NOUN", yytext); }
"gens"                       { emit("NOUN", yytext); }
"gros"                       { emit("ADJ", yytext); }
"hala"                       { emit("VERB", yytext); }
"haus"                       { emit("NOUN", yytext); }
"hein"                       { emit("PART", yytext); }
"hevi"                       { emit("ADJ", yytext); }
"hier"                       { emit("ADV", yytext); }
"hmmm"                       { emit("NOUN", yytext); }
"huit"                       { emit("NUM", yytext); }
"jasi"                       { emit("VERB", yytext); }
"jong"                       { emit("VERB", yytext); }
"jour"                       { emit("NOUN", yytext); }
"juju"                       { emit("NOUN", yytext); }
"kari"                       { emit("VERB", yytext); }
"kick"                       { emit("VERB", yytext); }
"klin"                       { emit("VERB", yytext); }
"klin"                       { emit("ADJ", yytext); }
"klos"                       { emit("NOUN", yytext); }
"kolo"                       { emit("NOUN", yytext); }
"krai"                       { emit("VERB", yytext); }
"kuki"                       { emit("VERB", yytext); }
"kwik"                       { emit("ADJ", yytext); }
"laik"                       { emit("VERB", yytext); }
"lait"                       { emit("NOUN", yytext); }
"lait"                       { emit("ADJ", yytext); }
"lent"                       { emit("ADJ", yytext); }
"leta"                       { emit("ADV", yytext); }
"leur"                       { emit("POSS", yytext); }
"long"                       { emit("ADJ", yytext); }
"mais"                       { emit("CONJ", yytext); }
"make"                       { emit("MAKE", yytext); }
"mama"                       { emit("NOUN", yytext); }
"mami"                       { emit("NOUN", yytext); }
"mboa"                       { emit("NOUN", yytext); }
"mbom"                       { emit("NOUN", yytext); }
"mbut"                       { emit("NOUN", yytext); }
"mbut"                       { emit("ADJ", yytext); }
"meme"                       { emit("PART", yytext); }
"mere"                       { emit("NOUN", yytext); }
"meuf"                       { emit("NOUN", yytext); }
"mois"                       { emit("NOUN", yytext); }
"mola"                       { emit("NOUN", yytext); }
"moni"                       { emit("NOUN", yytext); }
"mota"                       { emit("NOUN", yytext); }
"moto"                       { emit("NOUN", yytext); }
"muna"                       { emit("NOUN", yytext); }
"nain"                       { emit("NUM", yytext); }
"nait"                       { emit("NOUN", yytext); }
"nang"                       { emit("VERB", yytext); }
"ndem"                       { emit("VERB", yytext); }
"neba"                       { emit("NOUN", yytext); }
"neuf"                       { emit("NUM", yytext); }
"njoh"                       { emit("ADV", yytext); }
"nkap"                       { emit("NOUN", yytext); }
"nous"                       { emit("PRON", yytext); }
"nuit"                       { emit("NOUN", yytext); }
"ofis"                       { emit("NOUN", yytext); }
"onda"                       { emit("PREP", yytext); }
"opep"                       { emit("NOUN", yytext); }
"paie"                       { emit("VERB", yytext); }
"pain"                       { emit("NOUN", yytext); }
"papa"                       { emit("NOUN", yytext); }
"part"                       { emit("VERB", yytext); }
"pays"                       { emit("NOUN", yytext); }
"pepe"                       { emit("NOUN", yytext); }
"pere"                       { emit("NOUN", yytext); }
"peut"                       { emit("TMA", yytext); }
"peux"                       { emit("TMA", yytext); }
"piak"                       { emit("VERB", yytext); }
"piol"                       { emit("NOUN", yytext); }
"plei"                       { emit("VERB", yytext); }
"plus"                       { emit("NEG", yytext); }
"pour"                       { emit("PREP", yytext); }
"pret"                       { emit("ADJ", yytext); }
"prix"                       { emit("NOUN", yytext); }
"quel"                       { emit("QWORD", yytext); }
"quoi"                       { emit("PART", yytext); }
"quoi"                       { emit("QWORD", yytext); }
"rais"                       { emit("NOUN", yytext); }
"rait"                       { emit("VERB", yytext); }
"rich"                       { emit("ADJ", yytext); }
"rien"                       { emit("NEG", yytext); }
"rish"                       { emit("VERB", yytext); }
"sabi"                       { emit("VERB", yytext); }
"sait"                       { emit("VERB", yytext); }
"sale"                       { emit("ADJ", yytext); }
"sans"                       { emit("PREP", yytext); }
"sape"                       { emit("ADJ", yytext); }
"sawa"                       { emit("ADJ", yytext); }
"sens"                       { emit("NOUN", yytext); }
"sept"                       { emit("NUM", yytext); }
"sera"                       { emit("COP", yytext); }
"shem"                       { emit("NOUN", yytext); }
"shop"                       { emit("NOUN", yytext); }
"shot"                       { emit("ADJ", yytext); }
"shus"                       { emit("NOUN", yytext); }
"shwa"                       { emit("VERB", yytext); }
"siks"                       { emit("NUM", yytext); }
"sing"                       { emit("VERB", yytext); }
"skin"                       { emit("NOUN", yytext); }
"skul"                       { emit("NOUN", yytext); }
"slip"                       { emit("VERB", yytext); }
"smol"                       { emit("ADJ", yytext); }
"soir"                       { emit("NOUN", yytext); }
"sont"                       { emit("COP", yytext); }
"sors"                       { emit("VERB", yytext); }
"soso"                       { emit("ADV", yytext); }
"sous"                       { emit("PREP", yytext); }
"soya"                       { emit("NOUN", yytext); }
"stei"                       { emit("VERB", yytext); }
"ston"                       { emit("NOUN", yytext); }
"suis"                       { emit("COP", yytext); }
"swit"                       { emit("NOUN", yytext); }
"swit"                       { emit("ADJ", yytext); }
"taim"                       { emit("NOUN", yytext); }
"tara"                       { emit("NOUN", yytext); }
"taxi"                       { emit("NOUN", yytext); }
"taya"                       { emit("VERB", yytext); }
"tcha"                       { emit("VERB", yytext); }
"tide"                       { emit("ADV", yytext); }
"tink"                       { emit("VERB", yytext); }
"titi"                       { emit("NOUN", yytext); }
"toli"                       { emit("VERB", yytext); }
"tong"                       { emit("NOUN", yytext); }
"tori"                       { emit("NOUN", yytext); }
"tous"                       { emit("DET", yytext); }
"tout"                       { emit("DET", yytext); }
"tres"                       { emit("ADV", yytext); }
"trop"                       { emit("ADV", yytext); }
"vais"                       { emit("TMA", yytext); }
"vend"                       { emit("VERB", yytext); }
"vers"                       { emit("PREP", yytext); }
"veut"                       { emit("VERB", yytext); }
"veux"                       { emit("VERB", yytext); }
"vide"                       { emit("ADJ", yytext); }
"vite"                       { emit("ADV", yytext); }
"voir"                       { emit("VERB", yytext); }
"voit"                       { emit("VERB", yytext); }
"vont"                       { emit("TMA", yytext); }
"vous"                       { emit("PRON", yytext); }
"vrai"                       { emit("ADJ", yytext); }
"waka"                       { emit("VERB", yytext); }
"wata"                       { emit("NOUN", yytext); }
"wowo"                       { emit("ADJ", yytext); }
"wuna"                       { emit("PRON", yytext); }
"yong"                       { emit("ADJ", yytext); }
"ail"                        { emit("NOUN", yytext); }
"aks"                        { emit("VERB", yytext); }
"ami"                        { emit("NOUN", yytext); }
"aux"                        { emit("PREP", yytext); }
"bad"                        { emit("ADJ", yytext); }
"bai"                        { emit("VERB", yytext); }
"bak"                        { emit("NOUN", yytext); }
"bed"                        { emit("NOUN", yytext); }
"beg"                        { emit("VERB", yytext); }
"bia"                        { emit("NOUN", yytext); }
"big"                        { emit("ADJ", yytext); }
"bin"                        { emit("TMA", yytext); }
"boi"                        { emit("NOUN", yytext); }
"bon"                        { emit("NOUN", yytext); }
"bon"                        { emit("VERB", yytext); }
"bon"                        { emit("ADJ", yytext); }
"bot"                        { emit("CONJ", yytext); }
"buk"                        { emit("NOUN", yytext); }
"car"                        { emit("CONJ", yytext); }
"ces"                        { emit("DET", yytext); }
"dai"                        { emit("VERB", yytext); }
"dat"                        { emit("DET", yytext); }
"dea"                        { emit("ADV", yytext); }
"deh"                        { emit("PART", yytext); }
"dei"                        { emit("COP", yytext); }
"dem"                        { emit("PRON", yytext); }
"des"                        { emit("DET", yytext); }
"dey"                        { emit("PART", yytext); }
"dey"                        { emit("COP", yytext); }
"dia"                        { emit("ADJ", yytext); }
"dis"                        { emit("DET", yytext); }
"dit"                        { emit("VERB", yytext); }
"dix"                        { emit("NUM", yytext); }
"dja"                        { emit("VERB", yytext); }
"djo"                        { emit("NOUN", yytext); }
"doa"                        { emit("NOUN", yytext); }
"don"                        { emit("TMA", yytext); }
"dur"                        { emit("ADJ", yytext); }
"eau"                        { emit("NOUN", yytext); }
"eni"                        { emit("DET", yytext); }
"eru"                        { emit("NOUN", yytext); }
"est"                        { emit("COP", yytext); }
"eux"                        { emit("PRON", yytext); }
"fam"                        { emit("NOUN", yytext); }
"fat"                        { emit("ADJ", yytext); }
"fea"                        { emit("NOUN", yytext); }
"fee"                        { emit("NOUN", yytext); }
"fes"                        { emit("NOUN", yytext); }
"fes"                        { emit("NUM", yytext); }
"fil"                        { emit("VERB", yytext); }
"fit"                        { emit("TMA", yytext); }
"fon"                        { emit("NOUN", yytext); }
"for"                        { emit("PREP", yytext); }
"fut"                        { emit("NOUN", yytext); }
"gaz"                        { emit("NOUN", yytext); }
"get"                        { emit("VERB", yytext); }
"gud"                        { emit("ADJ", yytext); }
"han"                        { emit("NOUN", yytext); }
"hat"                        { emit("NOUN", yytext); }
"hau"                        { emit("QWORD", yytext); }
"hed"                        { emit("NOUN", yytext); }
"het"                        { emit("NOUN", yytext); }
"hia"                        { emit("PART", yytext); }
"hia"                        { emit("VERB", yytext); }
"hie"                        { emit("NOUN", yytext); }
"hot"                        { emit("NOUN", yytext); }
"ici"                        { emit("ADV", yytext); }
"ils"                        { emit("PRON", yytext); }
"jam"                        { emit("NOUN", yytext); }
"kam"                        { emit("VERB", yytext); }
"kap"                        { emit("NOUN", yytext); }
"kol"                        { emit("NOUN", yytext); }
"kol"                        { emit("VERB", yytext); }
"kon"                        { emit("NOUN", yytext); }
"kot"                        { emit("NOUN", yytext); }
"laf"                        { emit("VERB", yytext); }
"lak"                        { emit("NOUN", yytext); }
"lan"                        { emit("VERB", yytext); }
"las"                        { emit("NUM", yytext); }
"lef"                        { emit("VERB", yytext); }
"les"                        { emit("DET", yytext); }
"lod"                        { emit("VERB", yytext); }
"los"                        { emit("VERB", yytext); }
"lov"                        { emit("VERB", yytext); }
"lui"                        { emit("PRON", yytext); }
"luk"                        { emit("VERB", yytext); }
"mal"                        { emit("ADV", yytext); }
"man"                        { emit("NOUN", yytext); }
"mes"                        { emit("POSS", yytext); }
"mit"                        { emit("NOUN", yytext); }
"moi"                        { emit("PRON", yytext); }
"mon"                        { emit("POSS", yytext); }
"mop"                        { emit("NOUN", yytext); }
"muf"                        { emit("INTERJ", yytext); }
"mun"                        { emit("NOUN", yytext); }
"mus"                        { emit("TMA", yytext); }
"naw"                        { emit("ADV", yytext); }
"nek"                        { emit("NOUN", yytext); }
"nga"                        { emit("NOUN", yytext); }
"nia"                        { emit("PREP", yytext); }
"non"                        { emit("INTERJ", yytext); }
"nos"                        { emit("NOUN", yytext); }
"nyu"                        { emit("ADJ", yytext); }
"oga"                        { emit("NOUN", yytext); }
"ont"                        { emit("TMA", yytext); }
"oui"                        { emit("INTERJ", yytext); }
"par"                        { emit("PREP", yytext); }
"pas"                        { emit("NEG", yytext); }
"pei"                        { emit("VERB", yytext); }
"peu"                        { emit("ADV", yytext); }
"put"                        { emit("VERB", yytext); }
"que"                        { emit("CONJ", yytext); }
"qui"                        { emit("QWORD", yytext); }
"ren"                        { emit("NOUN", yytext); }
"rid"                        { emit("VERB", yytext); }
"rod"                        { emit("NOUN", yytext); }
"ron"                        { emit("VERB", yytext); }
"rue"                        { emit("NOUN", yytext); }
"rum"                        { emit("NOUN", yytext); }
"sec"                        { emit("NOUN", yytext); }
"sef"                        { emit("PART", yytext); }
"sel"                        { emit("VERB", yytext); }
"sha"                        { emit("PART", yytext); }
"six"                        { emit("NUM", yytext); }
"slo"                        { emit("ADJ", yytext); }
"sol"                        { emit("NOUN", yytext); }
"som"                        { emit("DET", yytext); }
"son"                        { emit("NOUN", yytext); }
"son"                        { emit("POSS", yytext); }
"sur"                        { emit("PREP", yytext); }
"tay"                        { emit("VERB", yytext); }
"tek"                        { emit("VERB", yytext); }
"tel"                        { emit("VERB", yytext); }
"ten"                        { emit("NUM", yytext); }
"tif"                        { emit("VERB", yytext); }
"tin"                        { emit("ADJ", yytext); }
"toi"                        { emit("PRON", yytext); }
"tok"                        { emit("VERB", yytext); }
"ton"                        { emit("POSS", yytext); }
"top"                        { emit("ADJ", yytext); }
"tri"                        { emit("NUM", yytext); }
"tut"                        { emit("NOUN", yytext); }
"una"                        { emit("PRON", yytext); }
"une"                        { emit("DET", yytext); }
"vas"                        { emit("TMA", yytext); }
"vex"                        { emit("VERB", yytext); }
"wai"                        { emit("QWORD", yytext); }
"wan"                        { emit("NUM", yytext); }
"wan"                        { emit("VERB", yytext); }
"was"                        { emit("VERB", yytext); }
"weh"                        { emit("INTERJ", yytext); }
"wen"                        { emit("QWORD", yytext); }
"wet"                        { emit("VERB", yytext); }
"wik"                        { emit("NOUN", yytext); }
"wik"                        { emit("ADJ", yytext); }
"win"                        { emit("NOUN", yytext); }
"wit"                        { emit("PREP", yytext); }
"wok"                        { emit("VERB", yytext); }
"yia"                        { emit("NOUN", yytext); }
"ad"                         { emit("VERB", yytext); }
"ai"                         { emit("NOUN", yytext); }
"ai"                         { emit("TMA", yytext); }
"an"                         { emit("CONJ", yytext); }
"as"                         { emit("TMA", yytext); }
"au"                         { emit("PREP", yytext); }
"bi"                         { emit("COP", yytext); }
"ca"                         { emit("PRON", yytext); }
"ce"                         { emit("DET", yytext); }
"da"                         { emit("DET", yytext); }
"de"                         { emit("PREP", yytext); }
"de"                         { emit("COP", yytext); }
"di"                         { emit("TMA", yytext); }
"di"                         { emit("DET", yytext); }
"do"                         { emit("NOUN", yytext); }
"du"                         { emit("DET", yytext); }
"eh"                         { emit("INTERJ", yytext); }
"es"                         { emit("COP", yytext); }
"et"                         { emit("CONJ", yytext); }
"et"                         { emit("NUM", yytext); }
"fa"                         { emit("ADV", yytext); }
"fo"                         { emit("PREP", yytext); }
"gi"                         { emit("VERB", yytext); }
"go"                         { emit("PART", yytext); }
"go"                         { emit("NOUN", yytext); }
"go"                         { emit("VERB", yytext); }
"hu"                         { emit("QWORD", yytext); }
"ia"                         { emit("NOUN", yytext); }
"if"                         { emit("CONJ", yytext); }
"il"                         { emit("PRON", yytext); }
"je"                         { emit("PRON", yytext); }
"la"                         { emit("PART", yytext); }
"la"                         { emit("DET", yytext); }
"le"                         { emit("DET", yytext); }
"ma"                         { emit("POSS", yytext); }
"me"                         { emit("PRON", yytext); }
"mi"                         { emit("PRON", yytext); }
"na"                         { emit("COP", yytext); }
"ne"                         { emit("NEG", yytext); }
"ni"                         { emit("NOUN", yytext); }
"no"                         { emit("NEG", yytext); }
"oh"                         { emit("PART", yytext); }
"ol"                         { emit("ADJ", yytext); }
"ol"                         { emit("DET", yytext); }
"on"                         { emit("PRON", yytext); }
"ou"                         { emit("CONJ", yytext); }
"po"                         { emit("ADJ", yytext); }
"qu"                         { emit("CONJ", yytext); }
"sa"                         { emit("POSS", yytext); }
"se"                         { emit("PRON", yytext); }
"si"                         { emit("CONJ", yytext); }
"si"                         { emit("VERB", yytext); }
"so"                         { emit("CONJ", yytext); }
"ta"                         { emit("POSS", yytext); }
"te"                         { emit("PRON", yytext); }
"tu"                         { emit("NUM", yytext); }
"tu"                         { emit("PRON", yytext); }
"un"                         { emit("DET", yytext); }
"va"                         { emit("TMA", yytext); }
"wi"                         { emit("PRON", yytext); }
"ya"                         { emit("VERB", yytext); }
"ya"                         { emit("POSS", yytext); }
"yi"                         { emit("PRON", yytext); }
"yu"                         { emit("PRON", yytext); }
"a"                          { emit("TMA", yytext); }
"a"                          { emit("PREP", yytext); }
"a"                          { emit("PRON", yytext); }
"d"                          { emit("PREP", yytext); }
"i"                          { emit("PRON", yytext); }
"j"                          { emit("PRON", yytext); }
"l"                          { emit("DET", yytext); }
"m"                          { emit("PRON", yytext); }
"n"                          { emit("NEG", yytext); }
"s"                          { emit("PRON", yytext); }
"t"                          { emit("PRON", yytext); }

{DIGIT}+                   { emit("NUM", yytext); }
[.,!?;:]                     { emit("PUNCT", yytext); }
{WORD}                     { emit("UNKNOWN", yytext); }
[ \t\r\n]+                  ; /* skip whitespace */
.                            { emit("UNKNOWN", yytext); }

%%

int main(void) {
    yylex();
    return 0;
}

