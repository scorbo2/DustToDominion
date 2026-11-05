#!/usr/bin/env python3
"""Generate flat files of unique first and last names.

Usage:
    python3 generate_npc_names.py [--count N] [--seed N] [--outdir DIR]

Each output file is defined by a NameSpec: filename, a curated pool block,
a validation regex, and a seed offset. Adding a new name list means adding
one NameSpec + one pool block. Nothing else changes.

This script ensures zero duplicates and zero stray whitespace.
We also sort the generated list for easy visual scanning, so be sure
that the loader code randomizes before picking a name from here.
"""

import argparse
import random
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SEED = 20261104
DEFAULT_COUNT = 500

GIVEN_NAME_RE = re.compile(r"^[A-Z][A-Za-z'-]*$")
# Surnames may carry particles (De Boer, Van den Berg, Le Goff, O'Sullivan):
# first token capital-initialised, later tokens either case.
SURNAME_RE = re.compile(r"^[A-Z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*)*$")

FEMALE_POOL = """
Mary, Patricia, Jennifer, Linda, Elizabeth, Barbara, Susan, Margaret, Dorothy, Karen,
Helen, Sandra, Ashley, Donna, Carol, Ruth, Sharon, Michelle, Emily, Amanda,
Melissa, Deborah, Stephanie, Rebecca, Laura, Cynthia, Amy, Kathleen, Shirley, Angela,
Anna, Brenda, Pamela, Nicole, Emma, Samantha, Katherine, Christina, Joan, Virginia,
Carolyn, Maria, Diane, Julie, Joyce, Kelly, Janet, Tracy, Theresa, Ann,
Evelyn, Kimberly, Nancy, Vicki, Leslie, Denise, Erica, Danielle, Christine, Marie,
Anne, Gloria, Marsha, Teresa, Dawn, Colleen, Tiffany, Jacqueline, Eva, Beatrice,
Louise, Frances, Edna, Florence, Marjorie, Ethel, Gladys, Alice, Jean, Norma,
Rose, Catherine, Judith, Megan, Rachel, Heather, Kristin, Kristina, Tara, Beth,
Heather, Lynn, Jackie, Tricia, Carolyn, Betty, Julia, Ruby, Molly, Peg,
Olivia, Sophia, Isabella, Ava, Mia, Charlotte, Amelia, Harper, Abigail, Scarlett,
Victoria, Aria, Grace, Chloe, Penelope, Riley, Hannah, Hazel, Lily, Eleanor,
Nora, Zoe, Aurora, Violet, Stella, Lucy, Caroline, Audrey, Claire, Vivian,
Sadie, Skylar, Naomi, Ellie, Ivy, June, Wren, Elsie, Mabel, Cora,
Ada, Opal, Esther, Matilda, Clara, Josephine, Rosalie, Lydia, Harriet, Willow,
Georgia, Luna, Nova, Piper, Quinn, Rowan, Sienna, Edith, Agnes, Agatha,
Bridget, Fiona, Maeve, Deirdre, Sheena, Moira, Aisling, Niamh, Siobhan, Aoife,
Ciara, Roisin, Caoimhe, Orla, Iona, Ailsa, Isla, Skye, Brigid, Eithne,
Enya, Bronwen, Carys, Ffion, Gwendolyn, Seren, Teleri, Angharad, Eira, Nia,
Blodwen, Rhiannon, Bronwyn, Dilys, Mairi, Neve, Sorcha, Eileen, Kiera, Aoibheann,
Orlaith, Muireann, Flavia, Letitia, Ottilie, Hettie, Millicent, Winifred, Cordelia, Philippa,
Amelie, Camille, Juliette, Margaux, Elodie, Sylvie, Colette, Odette, Genevieve, Cecile,
Simone, Anais, Ophelie, Margot, Noelle, Ariane, Babette, Chantal, Christelle, Delphine,
Estelle, Odile, Pascale, Solange, Blanche, Aimee, Arlette, Bernadette, Brigitte, Capucine,
Clothilde, Constance, Daniele, Eloise, Francoise, Gaelle, Helene, Jeanne, Lorraine, Lucienne,
Madeleine, Marcelle, Michele, Monique, Noemie, Paulette, Prudence, Raymonde, Solene, Suzanne,
Therese, Yvette, Yvonne, Aveline, Fleur, Honorine, Iseult, Josephe, Perrette, Rolande,
Helga, Greta, Hildegard, Brunhilde, Ingrid, Astrid, Heidi, Gertrude, Elfriede, Sigrid,
Ursula, Ilse, Katrin, Jutta, Marlene, Renate, Hannelore, Edeltraud, Anneliese, Berta,
Emmi, Frieda, Gudrun, Hedwig, Irmgard, Johanna, Karla, Klara, Liesel, Lotte,
Margit, Meta, Monika, Nadja, Nina, Roswitha, Sabine, Sonja, Steffi, Susanne,
Waltraud, Wilhelmine, Antonia, Cornelia, Dorothea, Elisabeth, Franziska, Gabriele, Gisela, Henriette,
Inge, Katja, Leonie, Luise, Magdalena, Marianne, Mathilde, Melanie, Natalie, Pauline,
Ricarda, Silke, Tanja, Vera, Wibke, Adelheid, Bettina, Dagmar, Franka, Gerlinde,
Heike, Karoline, Konstanze, Margarethe, Marita, Mila, Nele, Petra, Regine, Simone,
Gianna, Francesca, Chiara, Alessia, Bianca, Carla, Fabrizia, Giuliana, Rosetta, Luciana,
Fiorella, Simonetta, Patrizia, Wanda, Agnese, Alfonsa, Assunta, Benedetta, Brunella, Concetta,
Cosima, Donatella, Elda, Franca, Gemma, Letizia, Liliana, Marcella, Nadia, Ornella,
Paola, Raffaella, Rossana, Sabina, Silvana, Stefania, Tiziana, Valeria, Vincenza, Viviana,
Adriana, Alessandra, Angelina, Antonietta, Arianna, Beatrice, Carmela, Caterina, Cecilia, Claudia,
Cristina, Eleonora, Elisa, Emilia, Ermelinda, Ester, Federica, Filomena, Fulvia, Gaia,
Giovanna, Giulia, Ida, Imelda, Lorenza, Luigia, Ottavia, Prisca, Vittoria, Ortensia,
Carmen, Pilar, Dolores, Consuelo, Marisol, Esperanza, Nuria, Paloma, Remedios, Charo,
Almudena, Araceli, Cinta, Encarna, Maravillas, Milagros, Purificacion, Reyes, Soledad, Trini,
Amparo, Concepcion, Cruz, Josefa, Leonor, Lucila, Manuela, Rosario, Salome, Virtudes,
Beatriz, Ines, Catarina, Margarida, Conceicao, Filomena, Graca, Idalina, Judite, Leocadia,
Odete, Zelia, Branca, Constanca, Fernanda, Helena, Lucia, Madalena, Mafalda, Ottilia,
Zofia, Katarzyna, Agnieszka, Bozena, Danuta, Halina, Iwona, Krystyna, Malgorzata, Grazyna,
Jolanta, Wieslawa, Beata, Dorota, Ewa, Elzbieta, Genowefa, Henryka, Jadwiga, Kazimiera,
Leokadia, Mariola, Miroslawa, Stanislawa, Zuzanna, Aleksandra, Bronislawa, Dobrawa, Edyta, Gabriela,
Hanna, Irena, Kinga, Klaudia, Lidia, Lucyna, Magdalena, Marcelina, Martyna, Michalina,
Nikola, Paulina, Roksana, Sylwia, Weronika, Bogumila, Czyoslawa, Filipa, Hiacynta, Kunegunda,
Svetlana, Tatiana, Olga, Natalia, Irina, Galina, Ludmila, Ekaterina, Anastasia, Daria,
Ksenia, Yulia, Valentina, Tamara, Larisa, Nadezhda, Alexandra, Polina, Varvara, Yelena,
Oksana, Lyudmila, Zoya, Raisa, Vera, Lubov, Praskovya, Avdotya, Aksinya, Glafira,
Kira, Yevdokia, Anfisa, Danica, Bogdana, Milena, Stanislava, Vesela, Zlata, Marta,
Aikaterini, Vasiliki, Eleni, Despina, Theodora, Ourania, Angeliki, Chrysanthe, Efthymia, Fotini,
Kalliope, Lamprini, Rania, Voula, Xeni, Anthi, Danai, Eftychia, Katerina, Vasso,
Thalia, Melina, Eurydiki, Paraskevi, Styliani, Athanasia, Chrysi, Daphne, Glykeria, Ifigenia,
Signy, Solveig, Torill, Kirsten, Lise, Aino, Anneli, Disa, Frida, Hilma,
Salla, Annika, Birgitta, Elin, Gunilla, Karin, Leena, Margareta, Raili, Sanna,
Tove, Tuula, Ulla, Alfhild, Asta, Brita, Edda, Anja, Elna, Eivor,
Gerda, Grethe, Gunvor, Hilda, Ingegerd, Laila, Liv, Malin, Maren, Randi,
Ragne, Siri, Thea, Vibeke, Aulikki, Solvei, Thyra, Alva, Disa, Eira,
Ioana, Lenuta, Doina, Viorica, Ecaterina, Marioara, Cornelia, Luminita, Mioara, Rodica,
Oana, Florentina, Georgeta, Ileana, Marilena, Sanda, Zamfira, Vasilica, Dumitrita, Eugenia,
Katalin, Zsuzsanna, Erzsebet, Sarolta, Piroska, Rozalia, Gyongyver, Zsuzsa, Zsofia, Reka,
Maja, Vesna, Dubravka, Sladjana, Danijela, Ivana, Jelena, Goranka, Zorka, Ljubica,
Radmila, Snezana, Olivera, Biljana, Dragana, Jasna, Mirjana, Stanimira, Violeta, Zlatka,
Miriam, Rosa, Golda, Devorah, Rivka, Chana, Frimet, Lea, Jytte, Sulo,
Anouk, Femke, Sanne, Janneke, Ineke, Imke, Trijntje, Wieke, Guusje, Nun,
Jitka, Vlasta, Dasa, Iva, Bleta, Timea, Brigita, Mojca, Katarina, Renata
"""

MALE_POOL = """
James, Robert, John, Michael, David, William, Richard, Joseph, Thomas, Christopher,
Charles, Daniel, Matthew, Anthony, Donald, Steven, Paul, Andrew, Kenneth, Joshua,
Kevin, Brian, George, Timothy, Ronald, Edward, Jason, Jeffrey, Ryan, Jacob,
Nicholas, Eric, Jonathan, Stephen, Larry, Justin, Scott, Brandon, Frank, Benjamin,
Gregory, Raymond, Samuel, Patrick, Alexander, Sean, Nathan, Peter, Kyle, Adam,
Arthur, Bruce, Carl, Douglas, Eugene, Gerald, Harvey, Keith, Lawrence, Martin,
Neil, Oliver, Philip, Ralph, Stanley, Terry, Todd, Victor, Wayne, Albert,
Ernest, Frederick, Harold, Henry, Joe, Johnny, Leonard, Roy, Russell, Alan,
Ivan, Billy, Barry, Clarence, Dennis, Earl, Floyd, Glenn, Gus, Howard,
Jack, Louis, Marvin, Maurice, Mike, Mortimer, Norman, Reggie, Ronnie, Steve,
Ted, Wallace, Wesley, Willie, Cecil, Clive, Kingsley, Piers, Nigel, Graham,
Trevor, Alistair, Callum, Ewan, Fraser, Iain, Angus, Hamish, Lachlan, Alasdair,
Struan, Torquil, Malcolm, Harry, Alfie, Archie, Oscar, Freddie, Theo, Rupert,
Sean, Liam, Cillian, Ronan, Oisin, Fionn, Declan, Aidan, Cian, Conor,
Darragh, Emmett, Finn, Killian, Tadhg, Lorcan, Cathal, Diarmuid, Eamon, Colm,
Padraig, Cormac, Brendan, Dermot, Tiernan, Ciaran, Osgar, Ronan, Aengus, Ronan,
Jean, Philippe, Alain, Bertrand, Gaston, Remy, Thibault, Etienne, Marcel, Henri,
Didier, Patrice, Yves, Loic, Bastien, Cedric, Damien, Fabrice, Gerard, Giles,
Gustave, Jerome, Lionel, Marc, Michel, Nicolas, Olivier, Pascal, Pierre, Quentin,
Rene, Roland, Serge, Sylvain, Tristan, Xavier, Achille, Adrien, Ambroise, Andre,
Anselme, Antoine, Barnabe, Basile, Benoit, Bernard, Clement, Constantin, Cyprien, Emile,
Erwan, Evariste, Felix, Florent, Francois, Gaspard, Ghislain, Godefroy, Ignace, Isidore,
Jacques, Jules, Julien, Ladislas, Lazare, Leo, Leon, Leopold, Luc, Lucien,
Maxime, Melchior, Modeste, Napoleon, Noel, Onuphre, Theophile, Timothee, Vianney, Wilfrid,
Klaus, Jurgen, Wolfgang, Hans, Dieter, Gerhard, Siegfried, Reinhard, Helmut, Uwe,
Albrecht, Bernhard, Burkhard, Detlef, Eckhard, Ferdinand, Franz, Gunter, Hartmut, Hermann,
Hubert, Karl, Ludwig, Manfred, Norbert, Otto, Rainer, Rudolf, Werner, Wilhelm,
Alwin, Anselm, Armin, Benno, Berthold, Conrad, Egmont, Emil, Erwin, Florian,
Gotthold, Gustav, Heinrich, Hugo, Joachim, Johannes, Josef, Justus, Konrad, Kurt,
Lorenz, Magnus, Maximilian, Oskar, Philipp, Siegmund, Tilmann, Ulrich, Valentin, Walter,
Winfried, Adalbert, Bernd, Christian, Dirk, Friedhelm, Gereon, Hartwig, Helmut, Jorg,
Kaspar, Kilian, Lutz, Meinolf, Otfried, Reinhold, Rolf, Sebastian, Siegbert, Theodor,
Till, Tobias, Udo, Volker, Wulf, Anton, Benedikt, Clemens, Dominik, Elias,
Fabian, Felix, Friedrich, Georg, Gottfried, Guido, Hannes, Ignaz, Jonas, Leonard,
Alessandro, Matteo, Luca, Giovanni, Vincenzo, Fabio, Riccardo, Umberto, Cesare, Andrea,
Antonio, Bernardo, Claudio, Corrado, Danilo, Dario, Emilio, Enzo, Ettore, Ezio,
Federico, Felice, Fiorenzo, Gennaro, Giorgio, Gino, Guido, Leandro, Leonardo, Lorenzo,
Luciano, Marcello, Marco, Mariano, Mauro, Michele, Moreno, Nunzio, Orlando, Paolo,
Pasquale, Pietro, Raffaello, Romano, Rosario, Salvatore, Sergio, Silvio, Tiziano, Tommaso,
Ugo, Valentino, Vittorio, Agostino, Alberico, Ambrogio, Anselmo, Bonifacio, Bruno, Carlo,
Cosimo, Dino, Domenico, Donato, Elio, Emanuele, Ernesto, Ferruccio, Gaetano, Gaspare,
Gervasio, Isidoro, Orazio, Saverio, Teodoro, Tobias, Tranquillo, Ubaldo, Virginio, Zenobio,
Alejandro, Javier, Iker, Alvaro, Gonzalo, Santiago, Ignacio, Rafael, Fernando, Alfonso,
Rodolfo, Sebastian, Mateo, Pablo, Diego, Adrian, Raul, Oscar, Jorge, Miguel,
Angel, Vicente, Ramon, Francisco, Jose, Manuel, Juan, Enrique, Alberto, Roberto,
Carlos, Pedro, Cesar, Esteban, Faustino, Fidel, Gaspar, German, Gustavo, Jaime,
Jesus, Joaquin, Julian, Julio, Leopoldo, Luis, Marcelo, Marcos, Martin, Ramiro,
Ricardo, Ruben, Santos, Tomas, Isidro, Jacinto, Justo, Laureano, Niceto, Onofre,
Joaquin, Joaquim, Tiago, Duarte, Vasco, Leonel, Simao, Bento, Gabriel, Henrique,
Jeronimo, Lourenco, Nuno, Rodrigo, Salvador, Teodoro, Xavier, Anselmo, Bernardo, Francisco,
Marek, Pawel, Grzegorz, Dariusz, Krzysztof, Andrzej, Zbigniew, Wieslaw, Slawomir, Tadeusz,
Bogdan, Czeslaw, Edmund, Eugeniusz, Henryk, Ireneusz, Jaroslaw, Kazimierz, Lech, Leszek,
Ludwik, Mieczyslaw, Miroslaw, Ryszard, Stanislaw, Stefan, Tomasz, Walenty, Wladyslaw, Zdzislaw,
Bartosz, Ignacy, Jakub, Jozef, Karol, Kamil, Maciej, Mateusz, Michal, Przemyslaw,
Rafal, Szymon, Waldemar, Wojciech, Bronislaw, Cyprian, Dyonizy, Emanuel, Fidelis, Gwidon,
Dmitry, Sergei, Andrei, Mikhail, Viktor, Yuri, Igor, Pavel, Nikolai, Aleksandr,
Alexei, Boris, Denis, Evgeny, Fyodor, Gleb, Grigory, Kirill, Leonid, Lev,
Maxim, Nikita, Oleg, Roman, Ruslan, Semyon, Stanislav, Stepan, Vasily, Vladimir,
Vyacheslav, Yakov, Ilya, Afanasy, Artemy, Danila, Efim, Filipp, Gavriil, Ignaty,
Matvei, Prokhor, Pyotr, Savva, Timofei, Trofim, Zakhar, Kuzma, Parkentiy, Sisoy,
Nikolaos, Georgios, Konstantinos, Dimitrios, Theodoros, Athanasios, Vasileios, Christos, Evangelos, Ioannis,
Panagiotis, Spyridon, Alexandros, Anestis, Andreas, Antonios, Efstratios, Eleftherios, Iason, Loukas,
Manolis, Michail, Nikos, Pantelis, Periklis, Stamatis, Stergios, Tasos, Thanos, Vangelis,
Zisis, Fanourios, Kyriakos, Lazaros, Ploutarchos, Tycho, Onisilos, Haralambos, Vlasios, Charalambos,
Bjorn, Soren, Leif, Anders, Nils, Lars, Sven, Torsten, Stig, Ake,
Arne, Egil, Erik, Frode, Gunnar, Hakon, Kjetil, Lasse, Mads, Olaf,
Per, Rasmus, Tage, Trygve, Ulf, Valdemar, Vemund, Alvar, Bjarne, Esben,
Geir, Gorm, Halfdan, Hallvard, Hemming, Ivar, Jorgen, Knut, Leiv, Stein,
Teitur, Vidar, Agnar, Andri, Bart, Didrik, Eiler, Falke, Gardar, Haldor,
Dumitru, Ion, Gheorghe, Vasile, Constantin, Liviu, Radu, Sorin, Traian, Florin,
Lucian, Aurel, Cornel, Dan, Emil, Ioan, Marin, Mircea, Nicolae, Octavian,
Petre, Pompiliu, Serban, Valeriu, Victor, Costel, Dorinel, Elie, Grigore, Iulian,
Dezso, Geza, Imre, Istvan, Lajos, Sandor, Tibor, Zoltan, Bela, Antal,
Balint, Benedek, Bertalan, Denes, Ede, Ferenc, Gabor, Gyula, Kalman, Krisztian,
Miklos, Tivadar, Vincze, Zsolt, Abraham, Adalbert, Coloman, Evermund, Gelu, Levente,
Dragan, Goran, Zoran, Milos, Nikola, Miroslav, Predrag, Slobodan, Branislav, Ljubomir,
Aleksandar, Dusan, Filip, Ilija, Jovan, Marko, Petar, Rade, Sasa, Zivko,
Lazar, Miodrag, Nebojsa, Radoslav, Svetozar, Uros, Vuk, Zeljko, Bogoljub, Gavrilo,
Jan, Kees, Sjoerd, Barend, Coen, Floris, Guus, Huub, Karel, Maarten,
Martijn, Rinus, Sander, Thijs, Wouter, Aad, Antoon, Cees, Daan, Egbert,
Fokke, Geurt, Hilbrand, Jasper, Koos, Lub, Meindert, Niek, Okke, Pier
"""

SURNAME_POOL = """
Smith, Brown, Williams, Jones, Taylor, Davies, Evans, Thomas, Roberts, Walker,
Wright, Robinson, Thompson, White, Watson, Jackson, Green, Harris, Cooper, Hill,
Clark, Mitchell, Turner, Collins, Edwards, Morris, Hall, Ward, Moore, King,
Scott, Baker, Davis, Miller, Wilson, Lee, Allen, Young, Adams, Nelson,
Carter, Phillips, Parker, Reed, Cook, Bailey, Richardson, Cox, Howard, Barnes,
Hudson, Fisher, Ellis, Stevens, Myers, Bradley, Hamilton, Graham, Wells, Reid,
Webb, Marshall, Gibson, Hunt, Fraser, Kennedy, West, Coleman, Burton, Sutton,
Holmes, Watts, Palmer, Hughes, Bennett, Russell, Griffiths, Oliver, Mason, Chapman,
Butler, Saunders, Barber, Fowler, Nash, Graves, Hodges, Lane, Potter, Blake,
Fox, Pratt, Vance, Worrall, Underwood, Hargreaves, Ives, Beckett, Calvert, Danby,
Murphy, Kelly, O'Sullivan, Walsh, O'Brien, Byrne, Ryan, O'Connor, O'Neill, Doyle,
McCarthy, Gallagher, Doherty, Lynch, Quinn, McLaughlin, Connolly, Daly, Maguire, Brennan,
Donnelly, Roche, Sweeney, Sheridan, Nolan, Keogh, Flanagan, Cusack, Hanrahan, Fahey,
Kavanagh, Tracy, O'Carroll, O'Gorman, O'Leary, O'Malley, O'Boyle, O'Hanlon, O'Keeffe, O'Meara,
O'Rourke, O'Shea, O'Toole, O'Grady, O'Halloran, O'Casey, O'Donnell, O'Reilly, MacBride, MacDonagh,
McGinness, Magennis, Whelan, Devlin, Grimes,
MacDonald, MacLeod, MacGregor, MacKenzie, Stewart, Cameron, Gordon, Wallace, Bruce, Douglas,
Ferguson, Duncan, Menzies, Chisholm, Sinclair, Arbuthnot, Carnegie, Drummond, Erskine, Forbes,
Hay, Keith, Lamont, Livingstone, Maclaren, Matheson, Robertson, Thomson, Balfour, Cumming,
Dunbar, Guthrie, Home, Ker, Lyle, Nairn, Ogilvy, Pringle, Rutherford, Seton,
Urquhart, Wedderburn, Gladstone, Kinnaird, Marjoribanks,
Martin, Bernard, Dubois, Richard, Petit, Durand, Leroy, Moreau, Simon, Laurent,
Lefebvre, Michel, David, Bertrand, Vincent, Roux, Fournier, Girard, Bonnet, Dupont,
Lambert, Benoit, Mercier, Blanc, Guerin, Henry, Faure, Rousseau, Chevalier, Robin,
Masson, Garnier, Colin, Aubert, Perrin, Remy, Leclerc, Duval, Marchand, Le Goff,
Dujardin, Toussaint, Lemoine, Renaud, Dumas, Regnault, Vasseur, Lepage, Moulin, Brun,
Poirier, Marchal, Clement, Rousset, Barrier, Rolland, Barbier, Pescheur, Boucher, Gauthier,
Muller, Schmidt, Schneider, Fischer, Weber, Meyer, Wagner, Becker, Schulz, Hoffmann,
Koch, Richter, Klein, Wolf, Schroeder, Neumann, Schwarz, Zimmermann, Braun, Hartmann,
Lange, Werner, Schmitz, Krause, Meier, Lehmann, Schmid, Schulze, Maier, Koehler,
Huber, Kaiser, Popp, Fuchs, Weiss, Hess, Wolff, Hermann, Kruger, Busch,
Jager, Brandt, Haas, Beier, Decker, Engel, Fiedler, Geiger, Graf, Hamann,
Hirsch, Jacobi, Jung, Kaufmann, Keller, Kirchner, Kuhn, Langer, Lohmann, Marquardt,
Metzger, Mohr, Nagel, Peters, Preuss, Roth, Sachs, Schaefer, Schiller, Schmitt,
Schoen, Schuster, Seidel, Sommer, Stahl, Stein, Ullrich, Vogel, Voss, Walz,
Zeller, Zimmer, Gruber, Pichler, Steiner, Aigner, Altmann, Arnold, Baumann, Brandis,
Rossi, Russo, Ferrari, Esposito, Bianchi, Romano, Colombo, Ricci, Marino, Greco,
Bruno, Galli, Conti, Mancini, Giordano, Costa, Rizzo, Lombardi, Moretti, Barbieri,
Fontana, Testa, Marchetti, Marini, Leone, Longo, Gentile, Martinelli, Vitale, Ferri,
Gatti, Serra, Monti, De Luca, Coppola, Villa, Ferrara, Conte, Caruso, Farina,
Guerra, Pellegrini, Santoro, Milani, Orlandi, Rinaldi, Ranieri, Santini, Rosati, Gallo,
Amato, Fabbri, Montanari, Neri, D'Angelo, D'Amico, Lombardo, Abbate, Sanna, Piras,
Garcia, Fernandez, Lopez, Gomez, Gonzalez, Rodriguez, Sanchez, Perez, Jimenez, Ruiz,
Hernandez, Diaz, Alvarez, Romero, Torres, Ramirez, Flores, Molina, Herrera, Delgado,
Castro, Ortiz, Morales, Iglesias, Navarro, Medina, Guerrero, Cabrera, Ferrer, Pena,
Nunez, Arias, Campos, Vega, Leon, Ibanez, Serrano, Lozano, Vasquez, Cortes,
Fuentes, Rubio, Montoya, Salazar, Delgado,
Silva, Santos, Pereira, Oliveira, Ferreira, Sousa, Ribeiro, Carvalho, Martins, Almeida,
Cardoso, Teixeira, Correia, Mendes, Ramos, Tavares, Azevedo, Fonseca, Coelho, Amaral,
Pinheiro, Matos, Cunha, Abreu, Freitas, Pinto, Rocha, Antunes, Furtado, Valente,
Nowak, Kowalski, Wisniewski, Wojcik, Kowalczyk, Kaminski, Lewandowski, Zielinski, Szymanski, Wozniak,
Dabrowski, Kozlowski, Jankowski, Mazur, Kwiatkowski, Krawczyk, Kaczmarek, Zalewski, Grabowski, Pawlowski,
Michalski, Nowicki, Adamski, Wieczorek, Slomka, Gorski, Stanek, Baran, Zietek, Makowski,
Urban, Czarnecki, Sikora, Olszewski,
Ivanov, Smirnov, Kuznetsov, Popov, Sokolov, Lebedev, Kozlov, Novikov, Morozov, Petrov,
Volkov, Vasiliev, Zaitsev, Pavlov, Semenov, Golubev, Vinogradov, Bogdanov, Voronin, Tarasov,
Belov, Komarov, Orlov, Kiselev, Makarov, Maksimov, Shevchenko, Bondarenko, Tkachenko, Kovalenko,
Melnyk, Boyko, Kravchenko, Romanenko, Savchenko, Gritsenko,
Papadopoulos, Ioannou, Georgiou, Nikolaou, Dimitriou, Konstantinou, Papadakis, Papanikolaou, Katsaros, Economou,
Antoniou, Kyriakou, Vasileiou, Alexandrou, Stephanou, Christodoulou, Mavridis, Dimitriadis, Karagiannis, Papageorgiou,
Oikonomou, Theodorou, Angelopoulos, Vlachos, Karalis, Platis,
Johansson, Andersson, Karlsson, Nilsson, Eriksson, Larsson, Olsson, Persson, Svensson, Gustafsson,
Hansen, Andersen, Jensen, Larsen, Pedersen, Nilsen, Kristensen, Jorgensen, Petersen, Madsen,
Christensen, Henriksen, Iversen, Dahl, Lund, Holm, Strand, Solberg, Haugen, Virtanen,
Korhonen, Laine, Salminiemi, Hedlund, Sjostrom, Aalto,
Popescu, Ionescu, Georgescu, Stan, Stoica, Gheorghe, Rusu, Munteanu, Matei, Constantin,
Toma, Dinu, Neagu, Barbu, Lupu, Sandu, Vlad, Enache, Mocanu, Muresan,
Toth, Szabo, Kovacs, Varga, Nagy, Juhasz, Kiss, Horvath, Szilagyi, Farkas,
Balogh, Pinter, Lakatos, Szucs, Orban, Simon,
Horvat, Kovacevic, Jovanovic, Petrovic, Nikolic, Markovic, Djordjevic, Stojanovic, Ilic, Pavlovic,
Maric, Vukovic, Novakovic, Babic, Basic, Cermak, Dvorak, Prochazka, Svoboda, Novotny,
Horak, Novak, Blaha, Vesely,
De Jong, De Vries, Van den Berg, Van Dijk, De Boer, Bakker, Visser, Smit, Meijer, Bos,
Vos, Van der Meer, Kok, Post, Kuiper, Blok, Maas, Jansen, De Groot, Brink,
Hendriks, Willems, Claessen, Peeters, Verhoeven
"""


@dataclass(frozen=True)
class NameSpec:
    """One output file: a pool block, the regex its names must satisfy, and a seed offset."""

    filename: str
    pool_block: str
    name_re: re.Pattern
    seed_offset: int


SPECS = (
    NameSpec("npc_first_names_female.txt", FEMALE_POOL, GIVEN_NAME_RE, 0),
    NameSpec("npc_first_names_male.txt", MALE_POOL, GIVEN_NAME_RE, 1),
    NameSpec("npc_last_names.txt", SURNAME_POOL, SURNAME_RE, 2),
)


def clean_pool(block: str, name_re: re.Pattern) -> list[str]:
    """Strip, validate against `name_re`, and de-duplicate (case-insensitive).

    The dedupe is case-insensitive on purpose: "Marie" and "marie" would
    otherwise sneak through as two different recruits.
    """
    seen: set[str] = set()
    names: list[str] = []
    for raw in block.replace(",", "\n").splitlines():
        name = raw.strip()
        if not name:
            continue
        if not name_re.match(name):
            raise ValueError(f"Malformed name candidate: {raw!r}")
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def sample_names(pool: list[str], count: int, seed: int) -> list[str]:
    """Draw `count` unique names from `pool` in random order."""
    if len(pool) < count:
        raise SystemExit(f"Pool too small: need {count}, have {len(pool)}")
    rng = random.Random(seed)
    return rng.sample(pool, count)


def write_flat_file(path: Path, names: list[str]) -> None:
    path.write_text("\n".join(names) + "\n", encoding="utf-8")


def verify(path: Path, count: int) -> None:
    """Post-write audit: exact line count, uniqueness, no stray whitespace, sorted."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == count, f"{path}: {len(lines)} lines, expected {count}"
    assert len({n.lower() for n in lines}) == count, f"{path}: duplicates found"
    assert all(n == n.strip() and n for n in lines), f"{path}: stray whitespace or blank line"
    assert lines == sorted(lines, key=str.lower), f"{path}: not sorted alphabetically"
    print(f"VERIFIED {path.name}: {len(lines)} unique names, sorted A-Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="names per file")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="base RNG seed")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="output directory (default: script's own directory)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for spec in SPECS:
        pool = clean_pool(spec.pool_block, spec.name_re)
        print(f"{spec.filename}: pool of {len(pool)} unique names")
        chosen = sample_names(pool, args.count, args.seed + spec.seed_offset)
        # Sort case-insensitive so particles (De, Van) interleave properly.
        chosen = sorted(chosen, key=str.lower)
        out_path = args.outdir / spec.filename
        write_flat_file(out_path, chosen)
        verify(out_path, args.count)


if __name__ == "__main__":
    main()
