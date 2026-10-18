"""
Tests for pdf_to_ubls.py.

Covers:
- Third parties loading (VAT and country normalization)
- Grouping of the journal lines by document
- VAT categories (standard, partially exempt, exempt, reverse charge)
- UBL generation
- Conversion of the sample PDF in docs/
"""

import glob
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal

from openpyxl import Workbook

from pdf_to_ubls import (
    NS, build_invoice_data, build_ubl, group_documents, load_suppliers, main,
    normalize_country, normalize_vat,
)

DOCS = os.path.join(os.path.dirname(__file__), '..', 'docs')
SAMPLE_PDF = os.path.join(DOCS, '2025.05.FA.pdf')
SAMPLE_TIERS = os.path.join(DOCS, 'Tiers.xlsx')

SUPPLIERS = {
    '47': {'key': '000047', 'name': 'ING', 'vat': 'BE0403200393', 'street': 'Avenue Marnix 24',
           'postal_code': '1000', 'city': 'Bruxelles', 'country': 'BE', 'contact': '', 'phone': '',
           'email': '', 'bank_account': ''},
    '113': {'key': '000113', 'name': 'Google', 'vat': 'IE6388047V', 'street': '', 'postal_code': '',
            'city': '', 'country': 'IE', 'contact': '', 'phone': '', 'email': '', 'bank_account': ''},
}


def line(piece, type_, account, label, debit=None, credit=None, comment=''):
    return {
        'Date': '30.06.25', 'Pièce': piece, 'Type': type_, 'Compte': account, 'Libellé': label,
        'Débit': Decimal(debit) if debit else None, 'Crédit': Decimal(credit) if credit else None,
        'Commentaire': comment,
    }


def document(*lines):
    return group_documents(lines)[0]


def find(root, path):
    return root.find(path, NS).text


class TestNormalization(unittest.TestCase):

    def test_vat(self):
        self.assertEqual(normalize_vat('BE 0445.314.330'), 'BE0445314330')
        self.assertEqual(normalize_vat('BE'), '')
        self.assertEqual(normalize_vat('ZZ0000000303'), '')
        self.assertEqual(normalize_vat(None), '')

    def test_country(self):
        self.assertEqual(normalize_country('B'), 'BE')
        self.assertEqual(normalize_country('USA'), 'US')
        self.assertEqual(normalize_country('B', 'IE6388047V'), 'IE')
        self.assertEqual(normalize_country(None), 'BE')


class TestLoadSuppliers(unittest.TestCase):

    def test_load(self):
        wb = Workbook()
        ws = wb.active
        ws.append(['Clé Fournisseur', 'Nom', 'Id TVA', 'Adresse', 'Pays', 'C.Postal', 'Localité'])
        ws.append(['000113', 'Google', 'IE6388047V', None, 'B', None, None])
        ws.append(['000031', 'Resto', 'BE', None, 'B', None, None])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'tiers.xlsx')
            wb.save(path)
            suppliers = load_suppliers(path)

        self.assertEqual(suppliers['113']['name'], 'Google')
        self.assertEqual(suppliers['113']['country'], 'IE')
        self.assertEqual(suppliers['31']['vat'], '')
        self.assertEqual(suppliers['31']['country'], 'BE')


class TestGroupDocuments(unittest.TestCase):

    def test_group(self):
        documents = group_documents([
            line('F 1', 'F', '000031', 'Resto', credit='10.00'),
            line('F 1', 'G', '613310', 'FRAIS', debit='10.00'),
            line('F 2', 'F', '000031', 'Resto', credit='5.00'),
        ])
        self.assertEqual([d['piece'] for d in documents], ['F 1', 'F 2'])
        self.assertEqual(len(documents[0]['lines']), 2)


class TestBuildInvoiceData(unittest.TestCase):

    def test_standard_rate(self):
        data = build_invoice_data(document(
            line('F 6', 'F', '000047', 'ING', credit='104.24'),
            line('F 6', 'G', '411000', 'TVA DEDUCTIBLE', debit='18.09'),
            line('F 6', 'G', '600000', 'ACHATS', debit='86.15'),
        ), SUPPLIERS)
        self.assertEqual(data['id'], 'F6')
        self.assertEqual(data['date'], '2025-06-30')
        self.assertEqual(data['subtotals'], [
            {'category': 'S', 'rate': Decimal(21), 'taxable': Decimal('86.15'), 'tax': Decimal('18.09')}])
        self.assertEqual(len(data['lines']), 1)
        self.assertEqual(data['warnings'], [])

    def test_partially_exempt(self):
        data = build_invoice_data(document(
            line('F 38', 'F', '000047', 'ING', credit='12.76'),
            line('F 38', 'G', '411000', 'TVA DEDUCTIBLE', debit='1.26'),
            line('F 38', 'G', '656000', 'FRAIS DE BANQUE', debit='11.50'),
        ), SUPPLIERS)
        self.assertEqual([(s['category'], s['taxable']) for s in data['subtotals']],
                         [('S', Decimal('6.00')), ('E', Decimal('5.50'))])
        self.assertEqual([(l['category'], l['amount']) for l in data['lines']],
                         [('S', Decimal('6.00')), ('E', Decimal('5.50'))])

    def test_reverse_charge(self):
        data = build_invoice_data(document(
            line('F 15', 'F', '000113', 'Google', credit='57.50'),
            line('F 15', 'G', '411000', 'TVA DEDUCTIBLE', debit='12.08'),
            line('F 15', 'G', '451000', 'T.V.A. DUE', credit='12.08'),
            line('F 15', 'G', '600000', 'ACHATS', debit='57.50'),
        ), SUPPLIERS)
        self.assertEqual(data['subtotals'][0]['category'], 'K')
        self.assertEqual(data['vat'], Decimal(0))
        self.assertEqual(data['total'], Decimal('57.50'))

    def test_exempt_and_unknown_supplier(self):
        data = build_invoice_data(document(
            line('F 1', 'F', '000031', 'Resto', credit='74.50'),
            line('F 1', 'G', '613310', 'FRAIS DE RESTAURANT', debit='74.50'),
        ), SUPPLIERS)
        self.assertEqual(data['subtotals'][0]['category'], 'E')
        self.assertEqual(data['supplier']['name'], 'Resto')
        self.assertTrue(any('not found' in w for w in data['warnings']))

    def test_credit_note(self):
        data = build_invoice_data(document(
            line('F 9', 'F', '000047', 'ING', debit='12.10'),
            line('F 9', 'G', '411000', 'TVA DEDUCTIBLE', credit='2.10'),
            line('F 9', 'G', '600000', 'ACHATS', credit='10.00'),
        ), SUPPLIERS)
        self.assertTrue(data['credit_note'])
        self.assertEqual(data['total'], Decimal('12.10'))
        self.assertEqual(data['lines'][0]['amount'], Decimal('10.00'))


class TestBuildUbl(unittest.TestCase):

    def test_invoice(self):
        data = build_invoice_data(document(
            line('F 6', 'F', '000047', 'ING', credit='104.24', comment='Brico'),
            line('F 6', 'G', '411000', 'TVA DEDUCTIBLE', debit='18.09', comment='Brico'),
            line('F 6', 'G', '600000', 'ACHATS', debit='86.15', comment='Brico'),
        ), SUPPLIERS)
        root = build_ubl(data).getroot()

        self.assertEqual(root.tag, f"{{{NS['invoice']}}}Invoice")
        self.assertEqual(find(root, 'cbc:ID'), 'F6')
        self.assertEqual(find(root, 'cbc:InvoiceTypeCode'), '380')
        self.assertEqual(find(root, 'cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID'),
                         'BE0403200393')
        self.assertEqual(find(root, 'cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/'
                                    'cbc:RegistrationName'), 'CODOTRA')
        self.assertEqual(find(root, 'cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID'),
                         'BE0445314330')
        self.assertEqual(find(root, 'cac:TaxTotal/cbc:TaxAmount'), '18.09')
        self.assertEqual(find(root, 'cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent'), '21.00')
        self.assertEqual(find(root, 'cac:LegalMonetaryTotal/cbc:PayableAmount'), '104.24')
        self.assertEqual(find(root, 'cac:InvoiceLine/cbc:LineExtensionAmount'), '86.15')
        self.assertEqual(find(root, 'cac:InvoiceLine/cac:Item/cbc:Name'), 'ACHATS')


@unittest.skipUnless(os.path.isfile(SAMPLE_PDF) and os.path.isfile(SAMPLE_TIERS), 'sample files not available')
class TestSamplePdf(unittest.TestCase):

    def test_convert_sample_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main([SAMPLE_PDF, tmp]), 0)
            files = glob.glob(os.path.join(tmp, '*.xml'))
            total = sum(Decimal(find(ET.parse(f).getroot(), 'cac:LegalMonetaryTotal/cbc:PayableAmount'))
                        for f in files)

        # "Nb Doc: 40" and total of the suppliers account (440100) in the report
        self.assertEqual(len(files), 40)
        self.assertEqual(total, Decimal('4556.69'))

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(['does-not-exist.pdf', tmp]), 1)


if __name__ == '__main__':
    unittest.main()
