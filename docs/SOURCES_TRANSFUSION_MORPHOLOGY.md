# Transfusion and morphology/quality implementation notes

These modules are functional draft review aids requiring local validation. They do not release blood components, authorize laboratory reports, identify cells from images, or establish diagnoses. All clinical output wording, field choices, examples, and thresholds live in the corresponding JSON file. The common result preserves the normalized input, source references, version, and configuration hash.

## Transfusion

`logic/transfusion.py` implements ordinary RBC and plasma ABO tables with opposite donor/recipient directions. RhD applies to RBC review. Plasma review does not borrow RBC antibody-screen or crossmatch requirements. Neither pathway grants release authorization; emergency component substitutions, low-titre exceptions, neonatal workflows, and special products are outside this module.

The identity, specimen-validity, and independently verified type fields are conservative application gates requiring confirmation under the local SOP. An ABO discrepancy blocks the review. Current or historical antibody positivity routes through documented antibody workup, antigen-negative selection, and IAT crossmatch review. Symptoms reported during/after transfusion trigger the initial reaction escalation checklist without assigning a reaction diagnosis.

Primary references:

- [Lifeblood component compatibility](https://www.lifeblood.com.au/health-professionals/products/component-compatibility): RBC/plasma ABO direction and RhD scope.
- [Lifeblood pretransfusion collection and compatibility testing](https://www.lifeblood.com.au/health-professionals/clinical-practice/transfusion-process/pretransfusion-specimen-collection-compatibility-testing): specimen status, antibody history, electronic/immediate-spin restrictions, and IAT context.
- [Lifeblood suspected reaction management](https://www.lifeblood.com.au/health-professionals/clinical-practice/adverse-events/management-of-suspected-reactions): stop the transfusion, clinical assessment, IV access precautions, identity rechecks, and contact with the treating/transfusion teams.
- [ANZSBT laboratory guidelines, June 2025](https://anzsbt.org.au/wp-content/uploads/2025/06/Guidelines-for-transfusion-and-immunohaematology-laboratory-practice_June-2025-PUBLISHED-1.pdf): laboratory verification and local governance.

## Morphology and specimen quality

`logic/morphology_quality.py` records observations supplied by a human reviewer. Schistocyte review uses the population selected by the user: the configured upper reference is 1% for adults/full-term neonates and 5% for preterm neonates. Other children and unknown population receive no imported adult threshold. Exceeding a reference is a review signal, not a TMA diagnosis.

Specimen age is compared only with a supplied, explicitly validated local stability limit. There is no universal EDTA fill volume or specimen-storage duration. Clots, haemolysis, unsuitable fill, poor film quality, and platelet clumps create review holds. Important observations remain visible when other data are invalid.

Manual differential percentages require all eight cell categories to be entered as integer counts. Missing is not zero. A supplied total must equal their sum; a zero denominator is rejected. NRBCs stay outside the WBC differential denominator. Arithmetic does not confirm cell identity or specimen validity.

Primary references:

- [ICSH 2021 schistocyte update](https://www.icsh.org/2021-update-of-the-2012-icsh-recommendations-for-schistocytes): population-specific reference boundaries and interpretation limits.
- [ICSH 2015 morphology nomenclature and grading](https://www.icsh.org/recommendations-for-standardization-of-nomenclature-and-grading-of-peripheral-blood-cell): structured manual terminology.
- [ISLH consensus review rules](https://islh.org/web/consensus_rules.php): smear-review actions for abnormal-cell and platelet-clump observations; local validation remains necessary.
- [ICSH analyser evaluation guidance](https://doi.org/10.1111/ijlh.12201): validation of methods and sample stability.
- [BD collection-system instructions](https://www.bd.com/documents/alerts/Vacutainer%20Recall%20-%20Updated%20Package%20Insert.pdf): device-specific collection handling. Use the current instructions for the actual tube; this module supplies no universal fill limit.

The count, percentage, and elapsed-time input bounds are application validation limits rather than clinical reference intervals. No patient names, hospital numbers, free-text identifiers, or images are accepted by either module.
