# Asymmetric Numeral Systems (ANS)

This repository contains our implementations and experiments related to ANS, for our KiK (Coding and Cryptography) project.

For this project, we decided to implement entropy compression based on ANS created by Jarek Duda, Ph.D. This algorithm combines the speed of Huffman coding with the compression ratio of arithmetic coding.

### Architecture of the rANS (Range ANS) variant

We have implemented a variant of rANS (Range Asymmetric Numeral Systems). Its main idea is to represent the entire compressed data sequence as a single, large natural number, called the **encoder's state**.

The algorithm operates directly on probabilities and operates asymmetrically – more frequent symbols increase the state by a smaller amount (which costs fewer fractional bits), while less frequent symbols increase the state by a larger amount.

#### Model variable definitions
Before data is compressed, a statistical model of the file is determined. It uses the following parameters:
* $x$ – the current encoder state (usually a 32-bit or 64-bit variable),
* $s$ – the currently encoded symbol (in our case, a byte from 0 to 255),
* $f_s$ – the normalized frequency of the symbol $s$,
* $c_s$ – the cumulative distribution function (cumulative frequency) of all symbols preceding $s$ in the alphabet,
* $M$ – the sum of all normalized frequencies, acting as the denominator of the probability (usually a power of two, e.g., $M = 2^{12} = 4096$).

#### Encoding function
Encoding in rANS involves absorbing (encoding) the symbol $s$ into the current state $x$. The new state is calculated using a single mathematical operation:

$$x_{next} = \left\lfloor \frac{x}{f_s} \right\rfloor M + (x \bmod f_s) + c_s$$

Due to the asymmetry of this formula, the state $x$ grows at a rate inversely proportional to the probability of the symbol occurring. Mathematically, the symbol $s$ with probability $p = f_s / M$ increases the length of the encoded message by an optimal value close to $\log_2(1/p)$ bits.

#### Decoding function
Decompression in ANS systems is performed in the reverse order of compression (LIFO - *Last In, First Out* structure). We read the file backward. Given the state $x$, we first determine the so-called *slot*, which allows us to identify the encoded symbol:

$$slot = x \bmod M$$

Based on the value of *slot*, we search the dictionary (model array) for the symbol $s$ that satisfies the boundary condition:

$$c_s \le slot < c_s + f_s$$

After identifying symbol $s$ and writing it to the output buffer, the decoder state is reduced (the previous state is restored) using the inverse arithmetic operation:

$$x_{prev} = f_s \cdot \left\lfloor \frac{x}{M} \right\rfloor + slot - c_s$$

#### Bit streaming (Renormalization)
Because the physical variable storing the state $x$ in processor memory has a limited capacity (e.g., 32 bits), a constant increase in the state would quickly lead to an overflow. To prevent this, **renormalization** is used.

Before absorbing the next symbol, the program checks whether the state of $x$ exceeds a predefined limit. If it is too large, the least significant bits (e.g., an entire byte) are written to the physical target file, and the state of $x$ is reduced by a bitwise right shift. During decompression, this process occurs analogously – when the state of $x$ becomes too small, the missing bits are read from the compressed file.


## Silesia Corpus

The Silesia Corpus is a collection of files that covers common data types used today. File sizes range from 6 MB to 51 MB. It will be used to test our ANS encoding implementation.

### Silesia Corpus contents

| Filename | Description | Type | Source | Raw size [B] | Bzipped size [B] |
| :--- | :--- | :--- | :--- | ---: | ---: |
| **dickens** | Collected works of Charles Dickens | English text | Project Gutenberg | 10,192,446 | 2,799,528 |
| **mozilla** | Tarred executables of Mozilla 1.0 (Tru64 UNIX edition) | exe | Mozilla Project | 51,220,480 | 17,914,392 |
| **mr** | Medical magnetic resonance image | picture | Hospital image | 9,970,564 | 2,441,280 |
| **nci** | Chemical database of structures | database | CACTVS Chemical Info | 33,553,445 | 1,812,734 |
| **ooffice** | A dll from Open Office.org 1.01 | exe | Open Office | 6,152,192 | 2,862,526 |
| **osdb** | Sample database in MySQL format | database | OSDB Project | 10,085,684 | 2,802,792 |
| **reymont** | Text of the book Chłopi by Władysław Reymont | Polish pdf | Virtual Library | 6,627,202 | 1,246,230 |
| **samba** | Tarred source code of Samba 2-2.3 | src | Samba Project | 21,606,400 | 4,549,790 |
| **sao** | The SAO star catalog | bin data | SAO Star Catalog | 7,251,944 | 4,940,524 |
| **webster** | The 1913 Webster Unabridged Dictionary | html | Project Gutenberg | 41,458,703 | 8,644,714 |
| **xml** | Collected XML files | html | XMLPPM | 5,345,280 | 441,186 |
| **x-ray** | X-ray medical picture | picture | Hospital image | 8,474,240 | 4,051,112 |
| **Total** | | | | **211,938,580** | **54,506,808** |

## Source materials
* **[Original Paper by Jarek Duda](https://arxiv.org/pdf/1311.2540)**: *Asymmetric numeral systems: entropy coding combining speed of Huffman coding with compression rate of arithmetic coding* 
* **[A comprehensive 50-minute video presentation by Jarek Duda explaining the core concepts](https://www.youtube.com/watch?v=R5PeBBQw190)**: *Introduction to Asymmetric Numeral Systems*
* **[Wikipedia Overview](https://en.wikipedia.org/wiki/Asymmetric_numeral_systems)**
* **[Silesia Corpus](https://sun.aei.polsl.pl/~sdeor/index.php?page=silesia)**