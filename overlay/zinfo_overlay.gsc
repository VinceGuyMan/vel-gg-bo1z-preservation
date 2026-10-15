#include maps\_utility;
#include common_scripts\utility;
#include maps\_zombiemode_utility;

main( default_on )
{
	if ( GetDvar( #"zinfo" ) == "" )
	{
		SetDvar( "zinfo", default_on );
	}
	flag_wait( "all_players_connected" );

	last_alive = -1;
	last_left = -1;
	last_on = -1;
	last_send = 0;

	for ( ;; )
	{
		on = GetDvarInt( #"zinfo" ) != 0;
		alive = get_enemy_count();
		left = alive;
		if ( IsDefined( level.zombie_total ) && level.zombie_total > 0 )
		{
			left += level.zombie_total;
		}

		cur_round = 1;
		if ( IsDefined( level.round_number ) )
		{
			cur_round = level.round_number;
		}

		if ( on != last_on || ( on && ( alive != last_alive || left != last_left || GetTime() - last_send >= 3000 ) ) )
		{
			players = get_players();
			for ( i = 0; i < players.size; i++ )
			{
				players[i] SetClientDvars( "kisak_mod_tabinfo", on, "zinfo_alive", alive, "zinfo_left", left );
			}
			if ( on )
			{
				LogPrint( "zinfo: alive " + alive + " left " + left + " round " + cur_round + " t " + GetTime() + "\n" );
				PrintLn( "zinfo: alive " + alive + " left " + left + " round " + cur_round + " t " + GetTime() + "\n" );
			}
			last_on = on;
			last_alive = alive;
			last_left = left;
			last_send = GetTime();
		}
		wait( 0.25 );
	}
}
