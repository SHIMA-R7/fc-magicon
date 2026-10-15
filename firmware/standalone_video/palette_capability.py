"""6502 palette-read capability probe; invoked inside the VBlank handler."""
def emit_capability(a):
    def address(v):
        a.lda_imm(v>>8);a.sta(0x2006);a.lda_imm(v&255);a.sta(0x2006)
    def fill_palette():
        address(0x3f00);a.lda_zp(15)
        for _ in range(32):a.sta(0x2007)
    a.lda_zp(7);a.cmp_imm(2);a.bcc('cap_trial');a.jmp('cap_display')
    a.label('cap_trial')
    # Distinct underlying CIRAM data distinguishes delayed legacy reads.
    address(0x2f00);a.lda_imm(5)
    for _ in range(32):a.sta(0x2007)
    a.lda_zp(7);a.beq('cap_green');a.lda_imm(0x12);a.jmp('cap_target')
    a.label('cap_green');a.lda_imm(0x1a)
    a.label('cap_target');a.sta_zp(15);fill_palette()
    address(0x2f00);a.lda_abs(0x2007);a.lda_abs(0x2007)
    address(0x3f00)
    for i in range(32):
        a.lda_abs(0x2007);a.and_imm(0x3f)
        a.bytes_([0xc5,15],'CMP $0F');a.bne(f'cap_old_{i}')
        a.inc_zp(8);a.jmp(f'cap_next_{i}')
        a.label(f'cap_old_{i}');a.cmp_imm(5);a.bne(f'cap_other_{i}')
        a.inc_zp(9);a.jmp(f'cap_next_{i}')
        a.label(f'cap_other_{i}');a.inc_zp(11);a.label(f'cap_next_{i}')
    a.inc_zp(7);a.lda_zp(7);a.cmp_imm(2);a.beq('cap_result');a.jmp('restore')
    a.label('cap_result')
    for zp,port in ((8,0x5f24),(9,0x5f25),(11,0x5f26)):
        a.lda_zp(zp);a.sta(port)
    a.lda_zp(8);a.cmp_imm(64);a.bne('cap_check_old')
    a.lda_imm(2);a.jmp('cap_publish')
    a.label('cap_check_old');a.lda_zp(9);a.cmp_imm(64);a.bne('cap_uncertain')
    a.lda_imm(3);a.jmp('cap_publish')
    a.label('cap_uncertain');a.lda_imm(4)
    a.label('cap_publish');a.sta(0x5f20)
    a.lda_imm(0);a.sta_zp(12);a.sta_zp(13);a.jmp('restore')
    # Keep showing alternating known colours, independent of the read result.
    a.label('cap_display');a.inc_zp(13);a.lda_zp(13);a.cmp_imm(60)
    a.beq('cap_recolour');a.jmp('restore')
    a.label('cap_recolour');a.lda_imm(0);a.sta_zp(13)
    a.lda_zp(12);a.eor_imm(1);a.sta_zp(12);a.beq('cap_show_blue')
    a.lda_imm(0x1a);a.jmp('cap_show_colour')
    a.label('cap_show_blue');a.lda_imm(0x12)
    a.label('cap_show_colour');a.sta_zp(15);fill_palette();a.jmp('restore')
